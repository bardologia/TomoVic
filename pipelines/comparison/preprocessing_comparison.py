"""Comparison of preprocessing runs differing by multilook window size.

Measures profile sharpness, residual speckle, spurious peak count, and azimuth
correlation length on each run's tomogram, then reports the bias-variance
trade-off the window size controls.
"""

from __future__ import annotations

import json
import os

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses        import dataclass, field
from pathlib            import Path
from time               import perf_counter

import matplotlib.pyplot as plt
import numpy             as np

from pipelines.comparison.metric_table             import MetricTableRenderer
from pipelines.comparison.spatial_stats            import ContrastEstimator, SpatialDispersion
from tools.data.io            import FileIO
from tools.reporting.markdown import MarkdownDoc
from tools.reporting.plotting import PlotBase
from tools.monitoring.logger  import Logger


@dataclass
class WindowTrial:
    """One preprocessing run identified by its multilook window.

    Attributes:
        name          : Run tag under the preprocessing runs root.
        run_dir       : Directory of the preprocessing run.
        tomogram_path : Path of the full complex tomogram cube.
        window        : Multilook window as (height, width) in pixels.
        window_label  : Window rendered as "heightxwidth".
        window_area   : Number of pixels the window averages over.
        scene         : Scene identity of the run beyond its window: crop, stack identifier, polarisation, track selection and height range.
        metrics       : Measured metrics, filled in by WindowMetrics.
    """

    name          : str
    run_dir       : Path
    tomogram_path : Path
    window        : tuple
    window_label  : str
    window_area   : int
    scene         : dict
    metrics       : dict = field(default_factory=dict)


@dataclass
class WindowMeasurement:
    """Outcome of measuring one preprocessing trial.

    Attributes:
        metrics      : Comparison scalars as produced by `WindowMetrics._summarise`.
        chunks_read  : Number of range chunks measured.
        chunks_total : Number of range chunks the tomogram holds.
        duration_s   : Wall-clock seconds the measurement took.
    """

    metrics      : dict
    chunks_read  : int
    chunks_total : int
    duration_s   : float


class WindowTrialCollector:
    """Discovers preprocessing runs and reads their multilook window and scene identity.

    Attributes:
        REQUIRED_FILES : Outputs a run must hold to be measured, relative to the run directory.
        SCENE_FIELDS   : Config-state fields that must agree across the trials for the comparison to be about the window.
        runs_dir       : Root directory holding preprocessing runs.
        run_tags       : Explicitly requested run tags; empty means discover all.
        logger         : Logger used for discovery reporting.
    """

    REQUIRED_FILES = ("data/tomogram_full.npy", "meta/config_state.json")
    SCENE_FIELDS   = ("crop", "stack_identifier", "polarisation", "track_selection", "height_range")

    def __init__(self, runs_dir: Path, run_tags: list[str], logger: Logger) -> None:
        """Binds the collector to a runs root and the tags to compare.

        Args:
            runs_dir : Root directory holding preprocessing runs.
            run_tags : Run tags to compare; empty triggers discovery.
            logger   : Logger used for discovery reporting.
        """
        self.runs_dir = runs_dir
        self.run_tags = run_tags
        self.logger   = logger

    def _discover_tags(self) -> list[str]:
        """Returns the configured tags, or every run holding the required outputs, warning for each candidate directory that lacks one."""
        if self.run_tags:
            return list(self.run_tags)

        found   = []
        skipped = []
        for entry in sorted(self.runs_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith((".", "_")):
                continue

            missing = [relative for relative in self.REQUIRED_FILES if not (entry / relative).exists()]
            if missing:
                skipped.append(entry.name)
                self.logger.warning(f"{entry.name}: skipped, no {' or '.join(missing)}; its preprocessing is incomplete or failed")
                continue

            found.append(entry.name)

        if skipped:
            self.logger.warning(f"{len(skipped)} of {len(found) + len(skipped)} directories under {self.runs_dir} skipped for lacking preprocessing outputs: {', '.join(skipped)}")

        return found

    def _scene(self, state: dict) -> dict:
        """Returns the scene identity recorded in a run's config state: crop, stack identifier, polarisation, track selection and height range."""
        tomogram = state["tomogram_config"]

        return {
            "crop"             : state["crop"],
            "stack_identifier" : state["stack_identifier"],
            "polarisation"     : tomogram["polarisation"],
            "track_selection"  : tomogram["track_selection"],
            "height_range"     : list(tomogram["height_range"]),
        }

    def _build_trial(self, tag: str) -> WindowTrial:
        """Builds a trial by reading the tomogram filter window and the scene identity from the run's config state."""
        run_dir = self.runs_dir / tag
        state   = FileIO.load_json(run_dir / "meta" / "config_state.json")

        window = tuple(state["tomogram_config"]["filter_arguments"]["win"])
        label  = "x".join(str(int(value)) for value in window)
        area   = int(np.prod([int(value) for value in window]))

        return WindowTrial(
            name          = tag,
            run_dir       = run_dir,
            tomogram_path = run_dir / "data" / "tomogram_full.npy",
            window        = window,
            window_label  = label,
            window_area   = area,
            scene         = self._scene(state),
        )

    def _check_same_scene(self, trials: list[WindowTrial]) -> None:
        """Rejects trials that differ in anything but the window, since the report attributes every difference to it.

        Args:
            trials : Collected trials.

        Raises:
            ValueError : If a scene field takes more than one value across the trials, naming the field and every trial's value.
        """
        for key in self.SCENE_FIELDS:
            values = {trial.name: trial.scene[key] for trial in trials}

            if len({json.dumps(value, sort_keys=True) for value in values.values()}) > 1:
                listing = "; ".join(f"{name}: {value}" for name, value in values.items())
                raise ValueError(f"Preprocessing trials differ in {key}, so their windows are not comparable: {listing}. Name the runs of one scene in run_tags")

    def collect(self) -> list[WindowTrial]:
        """Collects the preprocessing trials to compare.

        Returns:
            Trials sorted by increasing multilook window area.

        Raises:
            ValueError : If the trials do not share crop, stack, polarisation, track selection and height range.
        """
        self.logger.section("Collecting preprocessing trials")

        trials = []
        for tag in self._discover_tags():
            trial = self._build_trial(tag)
            scene = ", ".join(f"{key}={value}" for key, value in trial.scene.items())
            self.logger.info(f"{trial.name:<48} window {trial.window_label}; {scene}")
            trials.append(trial)

        if not trials:
            self.logger.error(f"No preprocessing trials found under {self.runs_dir}")

        self._check_same_scene(trials)

        return sorted(trials, key=lambda item: item.window_area)


class WindowMetrics:
    """Measures tomogram sharpness and speckle statistics for one run.

    Attributes:
        pixel_sample : Approximate pixel budget; range chunks are subsampled to stay under it. Non-positive means measure every chunk.
        block_size   : Side length in pixels of the speckle-statistic blocks.
        range_chunk  : Number of range columns loaded per chunk.
        logger       : Logger used for progress reporting.
    """

    SPURIOUS_FRACTION = 0.3
    FLOOR_FRACTION    = 0.25

    def __init__(self, pixel_sample: int, block_size: int, range_chunk: int, logger: Logger) -> None:
        """Configures the sampling, block size, and chunking of the measurements.

        Args:
            pixel_sample : Approximate pixel budget, non-positive to use all.
            block_size   : Side length in pixels of the speckle-statistic blocks.
            range_chunk  : Number of range columns loaded per chunk.
            logger       : Logger used for progress reporting.
        """
        self.pixel_sample = pixel_sample
        self.block_size   = block_size
        self.range_chunk  = range_chunk
        self.logger       = logger

    def _range_starts(self, ranges: int, azimuths: int) -> list[int]:
        """Returns the range column indices at which chunks start.

        Args:
            ranges   : Total number of range columns in the tomogram.
            azimuths : Number of azimuth lines, used to convert the pixel budget into a column budget.

        Returns:
            Chunk start indices, evenly spread when the pixel budget forces a
            subsample and complete otherwise.
        """
        starts = list(range(0, ranges, self.range_chunk))

        if self.pixel_sample <= 0:
            return starts

        target_columns = self.pixel_sample // max(azimuths, 1)
        target_chunks  = max(1, -(-target_columns // self.range_chunk))

        if target_chunks >= len(starts):
            return starts

        picks = np.unique((((np.arange(target_chunks) + 0.5) * len(starts)) // target_chunks).astype(np.int64))

        return [starts[index] for index in picks]

    def _chunk_maps(self, amp: np.ndarray) -> tuple:
        """Computes the per-pixel maps of one range chunk.

        A local maximum counts as spurious when it exceeds SPURIOUS_FRACTION of
        the profile peak and is not the dominant peak itself.

        Args:
            amp : Tomogram amplitude of shape (elevation, azimuth, range_chunk).

        Returns:
            A tuple (contrast, peak, spurious) of shape (azimuth, range_chunk)
            each, holding the peak-to-floor contrast in dB, the peak amplitude,
            and the number of spurious competing peaks per profile.
        """
        contrast, peak = ContrastEstimator.contrast_from_amplitude(amp, self.FLOOR_FRACTION)

        middle   = amp[1:-1]
        is_peak  = (middle > amp[:-2]) & (middle >= amp[2:]) & (middle > self.SPURIOUS_FRACTION * peak[None, :, :])
        dominant = amp.argmax(axis=0) - 1
        interior = (dominant >= 0) & (dominant < is_peak.shape[0])
        at_peak  = np.take_along_axis(is_peak, np.clip(dominant, 0, is_peak.shape[0] - 1)[None, :, :], axis=0)[0]

        return contrast, peak, (is_peak.sum(axis=0) - (at_peak & interior)).astype(np.float32)

    def _summarise(self, contrast: np.ndarray, peak_map: np.ndarray, spurious_map: np.ndarray) -> dict:
        """Reduces the per-pixel maps to the comparison scalars.

        Args:
            contrast     : Peak-to-floor contrast in dB, shape (azimuth, range).
            peak_map     : Peak amplitude per profile, shape (azimuth, range).
            spurious_map : Spurious peak count per profile, same shape.

        Returns:
            Mapping with the valid-pixel fraction, contrast median and deciles
            in dB, median spurious peak count, block coefficient of variation,
            and azimuth correlation length in pixels.
        """
        valid = np.isfinite(contrast)

        return {
            "valid_fraction"        : float(valid.mean()),
            "contrast_db_median"    : float(np.nanmedian(contrast)),
            "contrast_db_p10"       : float(np.nanpercentile(contrast, 10)),
            "contrast_db_p90"       : float(np.nanpercentile(contrast, 90)),
            "spurious_peaks_median" : float(np.median(spurious_map[valid])),
            "speckle_cv_median"     : SpatialDispersion.block_cv(peak_map, self.block_size),
            "autocorr_length_az"    : SpatialDispersion.autocorr_length(peak_map, axis=0),
        }

    def compute(self, trial: WindowTrial) -> WindowMeasurement:
        """Streams a trial's tomogram in range chunks and returns its metrics with the chunk counts and the time taken.

        Args:
            trial : Trial whose tomogram of shape (elevation, azimuth, range) is memory-mapped and read chunk by chunk.

        Returns:
            The measurement holding the metrics produced by `_summarise`.
        """
        started = perf_counter()

        tomogram             = np.load(trial.tomogram_path, mmap_mode="r")
        _, azimuths, ranges  = tomogram.shape

        starts = self._range_starts(ranges, azimuths)
        total  = len(range(0, ranges, self.range_chunk))

        self.logger.subsection(f"Measuring {trial.name} (range chunks: {'all' if len(starts) == total else f'{len(starts)} of {total}'})")

        contrast_columns = []
        peak_columns     = []
        spurious_columns = []

        for start in starts:
            stop = min(start + self.range_chunk, ranges)
            amp  = np.abs(tomogram[:, :, start:stop]).astype(np.float32)

            contrast, peak, spurious = self._chunk_maps(amp)

            contrast_columns.append(contrast)
            peak_columns.append(peak)
            spurious_columns.append(spurious)

            del amp

        contrast_map = np.concatenate(contrast_columns, axis=1)
        peak_map     = np.concatenate(peak_columns,     axis=1)
        spurious_map = np.concatenate(spurious_columns, axis=1)

        return WindowMeasurement(self._summarise(contrast_map, peak_map, spurious_map), len(starts), total, perf_counter() - started)


class WindowComparisonPlots(PlotBase):
    """Bar plots of each comparison metric against the multilook window.

    Attributes:
        out_dir : Report directory; figures are written under `images/`.
    """

    PANELS = [
        ("contrast_db_median",    "Peak-to-floor contrast (dB)", "Profile sharpness vs window"),
        ("speckle_cv_median",     "Local coefficient of variation", "Residual speckle vs window"),
        ("spurious_peaks_median", "Spurious peaks per profile",   "Competing peaks vs window"),
        ("autocorr_length_az",    "Azimuth correlation length (px)", "Spatial blurring vs window"),
    ]

    def __init__(self, out_dir: Path) -> None:
        """Binds the plotter to the report output directory."""
        self.out_dir = out_dir

    def _bar(self, labels: list[str], values: list[float], y_label: str, title: str, path: Path):
        """Draws and saves one bar chart of a metric across windows.

        Args:
            labels  : Tick label per bar, the window over the dataset name.
            values  : Metric value per window, aligned with `labels`.
            y_label : Axis label including units where applicable.
            title   : Figure title.
            path    : Destination file for the figure.

        Returns:
            Path of the saved figure.
        """
        self._apply_style()

        fig, ax = plt.subplots(figsize=(max(6.0, 1.8 * len(labels)), 4.6))
        ax.bar(range(len(labels)), values, color="#3b6ea5", width=0.6)

        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=7)
        ax.set_xlabel("Window (height x width) and dataset")
        ax.set_ylabel(y_label)
        ax.set_title(title)

        fig.tight_layout()
        return self._save(fig, path)

    def render(self, trials: list[WindowTrial]) -> list[Path]:
        """Renders one bar chart per configured panel.

        Args:
            trials : Measured trials, ordered by window area.

        Returns:
            Paths of the saved figures, in panel order.
        """
        labels  = [f"{trial.window_label}\n{trial.name}" for trial in trials]
        written = []

        for key, y_label, title in self.PANELS:
            values = [trial.metrics[key] for trial in trials]
            path   = self.out_dir / "images" / f"{key}.png"
            written.append(self._bar(labels, values, y_label, title, path))

        return written


class WindowComparisonReport:
    """Markdown report of the multilook window bias-variance trade-off.

    Attributes:
        out_dir : Directory the report is written to.
        logger  : Logger used for progress reporting.
    """

    METRIC_COLUMNS = [
        ("valid_fraction",        "Valid frac"),
        ("contrast_db_median",    "Contrast dB"),
        ("speckle_cv_median",     "Speckle CV"),
        ("spurious_peaks_median", "Spurious"),
        ("autocorr_length_az",    "Corr len"),
    ]

    ORIENTATION = {
        "valid_fraction"        : "higher",
        "contrast_db_median"    : "higher",
        "speckle_cv_median"     : "lower",
        "spurious_peaks_median" : "lower",
        "autocorr_length_az"    : "lower",
    }

    def __init__(self, out_dir: Path, logger: Logger) -> None:
        """Binds the report to its output directory.

        Args:
            out_dir : Directory the report is written to.
            logger  : Logger used for progress reporting.
        """
        self.out_dir = out_dir
        self.logger  = logger

    def _table(self, doc: MarkdownDoc, trials: list[WindowTrial]) -> None:
        """Appends the per-window metric table to the document."""
        rows = MetricTableRenderer.render(
            rows           = trials,
            leading        = [("Dataset", lambda trial: f"`{trial.name}`"), ("Window", lambda trial: trial.window_label)],
            metric_columns = self.METRIC_COLUMNS,
            orientation    = self.ORIENTATION,
        )

        doc.heading("Per-window metrics", level=2)
        doc.raw("\n".join(rows))
        doc.blank()

    def _reading(self, doc: MarkdownDoc) -> None:
        """Appends the guide explaining how to read the trade-off across windows."""
        doc.heading("Reading the bias-variance trade-off", level=2)
        doc.paragraph("Arrows mark each axis on its own (↑ better, ↓ better) and the bold value is the per-column extreme, not an overall winner. As the multilook window grows, estimation variance falls: peak-to-floor contrast rises, residual speckle (local CV) drops, and spurious competing peaks per profile decrease. The cost is spatial resolution: the azimuth correlation length grows as neighbouring scatterers are mixed, so the largest window bolds the variance axes while the smallest bolds the correlation length. There is no single best window. Select the knee where variance has settled before the correlation length climbs, keep the two strongest candidates, and break the tie downstream on the end metric with a matched receptive field.")

    def _plots(self, doc: MarkdownDoc, plots: list[Path]) -> None:
        """Appends the comparison figures to the document."""
        doc.heading("Comparison plots", level=2)
        for path in plots:
            doc.image(path.stem, Path("images") / path.name)

    def write(self, trials: list[WindowTrial], plots: list[Path]) -> Path:
        """Writes the window comparison report.

        Args:
            trials : Measured trials to report on.
            plots  : Figures to embed; may be empty.

        Returns:
            Path of the written `report.md`.
        """
        doc = MarkdownDoc("Preprocessing window comparison")

        doc.paragraph(f"Compared {len(trials)} preprocessing trials differing by multilook window size.")

        self._table(doc, trials)
        if plots:
            self._plots(doc, plots)
        self._reading(doc)

        path = doc.save(self.out_dir / "report.md")
        self.logger.info(f"Report written to: {path}")
        return path


class PreprocessingComparisonPipeline:
    """Orchestrates collection, measurement, plotting, and reporting of window trials.

    Attributes:
        config  : Comparison entry configuration.
        out_dir : Directory the report and figures are written to.
        logger  : Logger used for progress reporting.
    """

    def __init__(self, config, out_dir: Path, logger: Logger) -> None:
        """Binds the pipeline to its configuration and output directory.

        Args:
            config  : Comparison entry configuration.
            out_dir : Directory the report and figures are written to.
            logger  : Logger used for progress reporting.
        """
        self.config  = config
        self.out_dir = out_dir
        self.logger  = logger

    def _collect(self) -> list[WindowTrial]:
        """Returns the preprocessing trials named or discovered by the configuration."""
        collector = WindowTrialCollector(Path(self.config.runs_dir), list(self.config.run_tags), self.logger)
        return collector.collect()

    def _worker_count(self, n_trials: int) -> int:
        """Returns the number of measurement threads, never exceeding the trial count."""
        requested = int(self.config.workers)
        if requested > 0:
            return min(requested, n_trials)

        return max(1, min(n_trials, (os.cpu_count() or 2)))

    def _measure(self, trials: list[WindowTrial]) -> None:
        """Fills each trial's `metrics` mapping in place, in parallel where allowed, logging one line as each trial finishes."""
        self.logger.section("Measuring trials")

        metrics = WindowMetrics(self.config.pixel_sample, self.config.block_size, self.config.range_chunk, self.logger)
        workers = self._worker_count(len(trials))

        self.logger.info(f"Measuring {len(trials)} trial(s) across {workers} worker(s)")

        finished = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(metrics.compute, trial): trial for trial in trials}

            for future in as_completed(futures):
                trial         = futures[future]
                result        = future.result()
                trial.metrics = result.metrics
                finished     += 1

                self.logger.ok(f"[{finished}/{len(trials)}] {trial.name}: {result.chunks_read} of {result.chunks_total} range chunks measured in {result.duration_s:.1f}s")

    def _plot(self, trials: list[WindowTrial]) -> list[Path]:
        """Returns the rendered comparison figures, empty when plotting is disabled."""
        if not self.config.make_plots:
            return []

        self.logger.section("Rendering comparison plots")

        return WindowComparisonPlots(self.out_dir).render(trials)

    def _report(self, trials: list[WindowTrial], plots: list[Path]) -> Path:
        """Returns the path of the written markdown report."""
        self.logger.section("Writing comparison report")

        return WindowComparisonReport(self.out_dir, self.logger).write(trials, plots)

    def run(self) -> Path:
        """Runs the full comparison and returns the written report path.

        Returns:
            Path of the written `report.md`.

        Raises:
            RuntimeError : If no preprocessing trial could be collected.
        """
        trials = self._collect()
        if not trials:
            raise RuntimeError("No preprocessing trials to compare")

        self._measure(trials)
        plots = self._plot(trials)

        report_path = self._report(trials, plots)

        self.logger.kv_table({
            "Trials Compared" : len(trials),
            "Plots Rendered"  : len(plots),
            "Report Path"     : str(report_path),
        })

        return report_path
