"""Collection of per-run inference reports into a single browsable directory.

Locates the Markdown reports written under a run's inference outputs, rewrites
their image references to absolute paths or embedded data URIs, and copies them
into a collector directory under names that identify their run.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing  import List

from configuration.diagnostics  import ReportCollectionConfig, ReportCollectionEntryConfig
from tools.data.io              import FileIO
from tools.reporting.reporting  import ReportAssets
from tools.runtime.run_selector import ReportRunSelector


class RunReportLocator:
    """Finds the report files inside one run's inference directory.

    Attributes:
        config: Collection config naming the run, the inference directory and
            the report filename.
    """

    def __init__(self, config: ReportCollectionConfig) -> None:
        """Initializes the locator with its collection config."""
        self.config = config

    def locate(self) -> List[Path]:
        """Returns the run's report paths, newest last.

        Returns:
            Every matching report path, or only the newest when the config sets
            latest_only.

        Raises:
            FileNotFoundError: If the inference directory is missing, or holds no
                report of the configured name.
        """
        inference_dir = self.config.inference_directory
        if not inference_dir.is_dir():
            raise FileNotFoundError(f"No '{self.config.inference_dirname}' directory at {inference_dir}; expected a training run directory holding inference outputs")

        reports = sorted(path for path in inference_dir.glob(f"*/{self.config.report_filename}") if path.is_file())
        if not reports:
            raise FileNotFoundError(f"No '{self.config.report_filename}' found in any inference output under {inference_dir}")

        if self.config.latest_only:
            return [reports[-1]]
        return reports


class ReportImageRewriter:
    """Rewrites a report's relative image links so it reads outside its own directory.

    Attributes:
        report_dir: Directory the original report lives in.
        embed_images: Inlines images as base64 data URIs when True, otherwise
            rewrites links to absolute paths.
        assets: Asset helper used to produce the data URIs.
        IMAGE_PATTERN: Markdown image syntax matched for rewriting.
        PASSTHROUGH: Link prefixes left untouched.
    """

    IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
    PASSTHROUGH   = ("data:", "http://", "https://")

    def __init__(self, report_path: Path, embed_images: bool) -> None:
        """Initializes the rewriter against the directory holding the report.

        Args:
            report_path: Report whose links are resolved relative to its parent.
            embed_images: Inlines images as data URIs when True.
        """
        self.report_dir   = Path(report_path).parent
        self.embed_images = embed_images
        self.assets       = ReportAssets(self.report_dir, embed_images=True)

    def _resolve(self, target: str) -> Path:
        """Returns the absolute path of a link target.

        Args:
            target: Link text taken from the Markdown image.

        Returns:
            The resolved absolute path.

        Raises:
            FileNotFoundError: If the referenced image does not exist.
        """
        path = Path(target)
        if not path.is_absolute():
            path = self.report_dir / path

        path = path.resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Report references a missing image: {target} (resolved to {path})")

        return path

    def _substitute(self, match: re.Match) -> str:
        """Returns one image link rewritten to a data URI or an absolute path."""
        label, target = match.group(1), match.group(2)
        if target.startswith(self.PASSTHROUGH):
            return match.group(0)

        path = self._resolve(target)
        src  = self.assets.src(path) if self.embed_images else path.as_posix()
        return f"![{label}]({src})"

    def rewrite(self, text: str) -> str:
        """Returns the report text with every local image link rewritten."""
        return self.IMAGE_PATTERN.sub(self._substitute, text)


class ReportCollection:
    """Collects one run's reports into the collector directory.

    Attributes:
        config: Collection config naming the run and the collector directory.
        logger: Logger for per-report progress.
    """

    def __init__(self, config: ReportCollectionConfig, logger) -> None:
        """Initializes the collection with its config and logger."""
        self.config = config
        self.logger = logger

    @staticmethod
    def run_label(run_dir: Path) -> str:
        """Returns the run's name, prefixed by its parent for seedN directories."""
        run_dir = Path(run_dir)
        if re.fullmatch(r"seed\d+", run_dir.name):
            return f"{run_dir.parent.name}_{run_dir.name}"
        return run_dir.name

    def _output_name(self, report_path: Path) -> str:
        """Returns the collected filename, qualified by the inference stamp when needed."""
        run_name = self.run_label(self.config.run_directory)
        if self.config.latest_only:
            return f"{run_name}.md"
        return f"{run_name}_{report_path.parent.name}.md"

    def _collect_one(self, report_path: Path) -> Path:
        """Rewrites one report's image links and writes it into the collector directory.

        Args:
            report_path: Source report inside the run's inference outputs.

        Returns:
            Path of the collected copy.
        """
        text        = report_path.read_text(encoding="utf-8")
        rewritten   = ReportImageRewriter(report_path, self.config.embed_images).rewrite(text)
        destination = Path(self.config.collector_dir) / self._output_name(report_path)

        destination.write_text(rewritten, encoding="utf-8")
        self.logger.ok(f"{report_path.parent.name}: collected as {destination.name}")
        return destination

    def run(self) -> dict:
        """Collects every located report of the run.

        Returns:
            Mapping with the run directory, collector directory, number of
            reports collected and their destination paths.
        """
        self.logger.subsection(f"Collecting reports: {Path(self.config.run_directory).name}")

        reports   = RunReportLocator(self.config).locate()
        collected = [self._collect_one(report_path) for report_path in reports]

        return {
            "run_directory"   : str(self.config.run_directory),
            "collector_dir"   : str(self.config.collector_dir),
            "n_reports"       : len(collected),
            "collected_paths" : collected,
        }


class ReportCollectionBatch:
    """Collects reports from every selected run into one collector directory.

    Attributes:
        entry_config: Entry config naming the runs directory, the run filter and
            the collector directory.
        logger: Logger for selection and summary messages.
    """

    def __init__(self, entry_config: ReportCollectionEntryConfig, logger) -> None:
        """Initializes the batch with its entry config and logger."""
        self.entry_config = entry_config
        self.logger       = logger

    def _select_runs(self) -> list[Path]:
        """Returns the run directories chosen by the configured run filter."""
        selector = ReportRunSelector(self.entry_config.runs_dir, self.entry_config.inference_dirname, self.entry_config.report_filename, self.logger)
        return selector.resolve(self.entry_config.run_filter)

    def _check_collisions(self, run_dirs: list[Path]) -> None:
        """Raises when two selected runs would produce the same collected filename.

        Args:
            run_dirs: Selected run directories.

        Raises:
            ValueError: If two runs share a label.
        """
        names      = [ReportCollection.run_label(run_dir) for run_dir in run_dirs]
        duplicates = sorted({name for name in names if names.count(name) > 1})

        if duplicates:
            raise ValueError(f"Selected runs share a name, their collected reports would collide: {duplicates}")

    def _collect_run(self, run_dir: Path) -> dict:
        """Collects one run's reports and returns its collection summary."""
        config = self.entry_config.to_config(run_dir)
        return ReportCollection(config, self.logger).run()

    def run(self) -> list[dict]:
        """Selects the runs, checks for name collisions and collects each one.

        Returns:
            One collection summary per run, in selection order.
        """
        self.logger.section(f"Report collection into {self.entry_config.collector_dir}")

        run_dirs = self._select_runs()
        self._check_collisions(run_dirs)

        FileIO.ensure_dirs(Path(self.entry_config.collector_dir))
        results = [self._collect_run(run_dir) for run_dir in run_dirs]

        self.logger.ok(f"Collected {sum(result['n_reports'] for result in results)} report(s) from {len(results)} run(s) into {self.entry_config.collector_dir}")
        return results
