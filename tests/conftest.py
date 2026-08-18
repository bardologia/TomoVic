"""Shared pytest fixtures and logging stubs for the whole test suite.

Session-scoped fixtures expose the gitignored test_data/ tree (preprocessed stacks,
and metadata); they skip when that tree is absent.
"""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from tools.monitoring.logger import Logger

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_TEST_DATA = _REPO_ROOT / "test_data"
_DATA      = _TEST_DATA / "data"
_META      = _TEST_DATA / "meta"

_HAS_DATA = _TEST_DATA.is_dir() and (_DATA / "dataset.json").is_file()


class SilentProgress:
    """Progress-bar stub that accepts task calls and does nothing.

    Stands in for the Rich progress handle yielded by Logger.track.
    """

    def add_task(self, *args, **kwargs):
        """Returns a fixed task identifier of zero."""
        return 0

    def advance(self, *args, **kwargs):
        """Ignores a progress advance."""
        pass

    def update(self, *args, **kwargs):
        """Ignores a progress update."""
        pass


class SilentLogger:
    """Logger stub whose reporting methods are all no-ops.

    Mirrors the public surface of tools.monitoring.logger.Logger so pipelines under
    test can log without producing output or files.
    """

    def section(self, *args, **kwargs):       pass
    def subsection(self, *args, **kwargs):    pass
    def debug(self, *args, **kwargs):         pass
    def info(self, *args, **kwargs):          pass
    def warning(self, *args, **kwargs):       pass
    def error(self, *args, **kwargs):         pass
    def critical(self, *args, **kwargs):      pass
    def ok(self, *args, **kwargs):            pass
    def render(self, *args, **kwargs):        pass
    def panel(self, *args, **kwargs):         pass
    def rule(self, *args, **kwargs):          pass
    def kv_table(self, *args, **kwargs):      pass
    def metrics_table(self, *args, **kwargs): pass
    def close(self, *args, **kwargs):         pass

    @contextlib.contextmanager
    def timer(self, label: str):
        """Yields control without timing the labelled block.

        Args:
            label: Ignored name of the timed section.
        """
        yield

    @contextlib.contextmanager
    def track(self, transient: bool = False):
        """Yields a SilentProgress in place of a live progress bar.

        Args:
            transient: Ignored flag for transient rendering.

        Yields:
            A progress stub that discards all task updates.
        """
        yield SilentProgress()

    progress_bar = track

    @contextlib.contextmanager
    def live_monitor(self, title: str = "Training Monitor"):
        """Yields a SilentProgress in place of the live training monitor.

        Args:
            title: Ignored monitor title.

        Yields:
            A progress stub that discards all task updates.
        """
        yield SilentProgress()


class RecordingLogger(SilentLogger):
    """Logger stub that records the messages it is asked to emit.

    Attributes:
        messages: List of (level, message) pairs in emission order.
    """

    def __init__(self):
        """Initialises an empty message log."""
        self.messages = []

    def section(self, msg):
        """Records a section heading."""
        self.messages.append(("section", msg))

    def subsection(self, msg):
        """Records a subsection heading."""
        self.messages.append(("subsection", msg))

    def ok(self, msg):
        """Records a success message."""
        self.messages.append(("ok", msg))

    def info(self, msg):
        """Records an informational message."""
        self.messages.append(("info", msg))

    def warning(self, msg):
        """Records a warning message."""
        self.messages.append(("warning", msg))

    def error(self, msg):
        """Records an error message."""
        self.messages.append(("error", msg))

    def metrics_table(self, rows, columns=None, title=None):
        """Records only the title of a metrics table, discarding the rows."""
        self.messages.append(("metrics_table", title))


def make_file_logger(tmp_path: Path, name: str) -> Logger:
    """Builds a real Logger writing under a temporary directory.

    Args:
        tmp_path: Directory that receives the logs/ subdirectory.
        name: Logger name used for the log file.

    Returns:
        A Logger configured to write inside tmp_path.
    """
    return Logger(log_dir=str(tmp_path / "logs"), name=name)


def _require_data():
    """Skips the calling test when the real test_data/ tree is missing."""
    if not _HAS_DATA:
        pytest.skip("real data not present under test_data/")


@pytest.fixture
def logger_stub() -> SilentLogger:
    """Returns a no-op logger stub."""
    return SilentLogger()


@pytest.fixture
def recording_logger() -> RecordingLogger:
    """Returns a logger stub that records emitted messages."""
    return RecordingLogger()


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Returns the repository root directory."""
    return _REPO_ROOT


@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    """Returns the test_data/ root, skipping when it is absent."""
    _require_data()
    return _TEST_DATA


@pytest.fixture(scope="session")
def data_dir() -> Path:
    """Returns the test_data/data directory holding the preprocessed arrays."""
    _require_data()
    return _DATA


@pytest.fixture(scope="session")
def meta_dir() -> Path:
    """Returns the test_data/meta directory holding dataset metadata."""
    _require_data()
    return _META


@pytest.fixture(scope="session")
def dataset_json(data_dir) -> dict:
    """Returns the parsed dataset.json manifest."""
    return json.loads((data_dir / "dataset.json").read_text())


@pytest.fixture(scope="session")
def config_state_json(meta_dir) -> dict:
    """Returns the parsed config_state.json of the preprocessing run."""
    return json.loads((meta_dir / "config_state.json").read_text())


@pytest.fixture(scope="session")
def baselines_json(meta_dir) -> dict:
    """Returns the parsed baselines.json acquisition metadata."""
    return json.loads((meta_dir / "baselines.json").read_text())


@pytest.fixture(scope="session")
def pass_labels(dataset_json) -> list:
    """Returns the ordered pass labels of the SAR stack."""
    return dataset_json["pass_labels"]


@pytest.fixture(scope="session")
def tomogram_full(data_dir) -> np.ndarray:
    """Returns the memory-mapped tomogram of shape (heights, azimuth, range)."""
    return np.load(data_dir / "tomogram_full.npy", mmap_mode="r")


@pytest.fixture(scope="session")
def dem_full(data_dir) -> np.ndarray:
    """Returns the memory-mapped DEM of shape (azimuth, range) in metres."""
    return np.load(data_dir / "dem_full.npy", mmap_mode="r")


@pytest.fixture(scope="session")
def primary(data_dir) -> np.ndarray:
    """Returns the memory-mapped primary SLC image of shape (azimuth, range)."""
    return np.load(data_dir / "primary.npy", mmap_mode="r")


@pytest.fixture(scope="session")
def secondaries(data_dir) -> np.ndarray:
    """Returns the memory-mapped secondary SLC stack of shape (tracks, azimuth, range)."""
    return np.load(data_dir / "secondaries.npy", mmap_mode="r")


@pytest.fixture(scope="session")
def interferograms(data_dir) -> np.ndarray:
    """Returns the memory-mapped interferogram stack of shape (tracks, azimuth, range)."""
    return np.load(data_dir / "interferograms.npy", mmap_mode="r")


@pytest.fixture(scope="session")
def track_profiles(data_dir) -> dict:
    """Returns the per-track reflectivity profiles keyed by array name."""
    npz = np.load(data_dir / "track_profiles.npz", allow_pickle=True)
    return {k: npz[k] for k in npz.files}


@pytest.fixture
def small_window():
    """Returns a 32x32 azimuth and range slice pair for cheap windowed reads."""
    return (slice(0, 32), slice(0, 32))
