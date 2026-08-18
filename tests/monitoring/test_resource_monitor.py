"""Tests covering ResourceMonitor: config loading, RAM and VRAM sampling, threshold warnings, the sampling thread, and NVML device selection."""

from __future__ import annotations

import time
import types

import pytest

import tools.monitoring.resource_monitor as rm
from tools.monitoring.resource_monitor import ResourceMonitor


class FakeConfig:
    """Stand-in monitoring config exposing every field ResourceMonitor reads.

    Attributes:
        enabled: Whether monitoring is active.
        poll_interval_sec: Sampling period in seconds.
        log_to_tensorboard: Whether samples are forwarded to the tracker.
        warn_ram_pct: RAM usage percentage above which a warning fires.
        warn_vram_pct: VRAM usage percentage above which a warning fires.
        warn_swap_pct: Swap usage percentage above which a warning fires.
        warn_shm_pct: Shared-memory usage percentage above which a warning fires.
        warn_cooldown_sec: Minimum seconds between two warnings sharing a key.
    """
    def __init__(self, **kwargs):
        """Builds a config whose unspecified fields take monitor-friendly defaults.

        Args:
            **kwargs: Field overrides keyed by attribute name.
        """
        self.enabled            = kwargs.get("enabled", True)
        self.poll_interval_sec  = kwargs.get("poll_interval_sec", 0.05)
        self.log_to_tensorboard = kwargs.get("log_to_tensorboard", True)
        self.warn_ram_pct       = kwargs.get("warn_ram_pct", 90.0)
        self.warn_vram_pct      = kwargs.get("warn_vram_pct", 90.0)
        self.warn_swap_pct      = kwargs.get("warn_swap_pct", 50.0)
        self.warn_shm_pct       = kwargs.get("warn_shm_pct", 80.0)
        self.warn_cooldown_sec  = kwargs.get("warn_cooldown_sec", 30.0)


class CollectingLogger:
    """Logger stub that stores every message it is handed.

    Attributes:
        warnings: Warning messages received.
        sections: Section titles received.
        subsections: Subsection titles received.
        kv_tables: Key-value tables received, each copied into a dict.
    """
    def __init__(self):
        """Creates the empty message buffers."""
        self.warnings    = []
        self.sections    = []
        self.subsections = []
        self.kv_tables   = []

    def warning(self, msg):
        """Stores a warning message."""
        self.warnings.append(msg)

    def section(self, msg):
        """Stores a section title."""
        self.sections.append(msg)

    def subsection(self, msg):
        """Stores a subsection title."""
        self.subsections.append(msg)

    def kv_table(self, data, *args, **kwargs):
        """Stores a copy of a key-value table."""
        self.kv_tables.append(dict(data))


class RecordingTracker:
    """Tracker stub recording every metrics batch it receives.

    Attributes:
        calls: Tuples of (prefix, metrics, step) in call order.
    """
    def __init__(self):
        """Creates the empty call buffer."""
        self.calls = []

    def log_metrics(self, prefix, metrics, step):
        """Records a metrics batch together with its prefix and step."""
        self.calls.append((prefix, dict(metrics), step))


@pytest.fixture
def cfg():
    """Returns a monitoring config with default thresholds and a fast poll interval."""
    return FakeConfig()


@pytest.fixture
def monitor(cfg):
    """Returns a monitor wired to a collecting logger and no tracker."""
    return ResourceMonitor(cfg, logger=CollectingLogger())


def test_load_config_reads_fields(cfg):
    """Verifies the monitor copies enabled, interval, and thresholds off the config."""
    m = ResourceMonitor(cfg, logger=None)

    assert m.enabled       is True
    assert m.interval      == 0.05
    assert m.warn_ram_pct  == 90.0
    assert m.warn_swap_pct == 50.0


def test_missing_config_field_raises():
    """Verifies a config missing the expected fields fails at construction."""
    with pytest.raises(AttributeError):
        ResourceMonitor(types.SimpleNamespace(), logger=None)


def test_renamed_config_field_raises():
    """Verifies a renamed poll-interval field is rejected by name rather than silently defaulted."""
    cfg = FakeConfig()
    cfg.poll_interval_s = cfg.poll_interval_sec
    del cfg.poll_interval_sec

    with pytest.raises(AttributeError, match="poll_interval_sec"):
        ResourceMonitor(cfg, logger=None)


def test_step_getter_default_is_zero(cfg):
    """Verifies the default step getter reports step zero."""
    m = ResourceMonitor(cfg, logger=None)

    assert m.step_getter() == 0


def test_bytes_to_gb():
    """Verifies byte counts convert to gibibytes."""
    assert ResourceMonitor._bytes_to_gb(1024 ** 3) == 1.0
    assert ResourceMonitor._bytes_to_gb(0)         == 0.0


def test_peak_initialised_to_zero(monitor):
    """Verifies the peak table starts at zero for the RAM and VRAM keys."""
    assert set(monitor.peak) >= {"ram_used_gb", "ram_pct", "vram_used_gb"}
    assert all(v == 0.0 for v in monitor.peak.values())


def test_sample_returns_cpu_mem_metrics(monitor):
    """Verifies a sample carries RAM totals, percentage, swap, process RSS, and CPU load."""
    metrics = monitor.sample()

    assert metrics["ram_used_gb"]      > 0.0
    assert metrics["ram_total_gb"]     > 0.0
    assert metrics["ram_available_gb"] > 0.0
    assert 0.0 <= metrics["ram_pct"] <= 100.0
    assert "swap_used_gb" in metrics
    assert "proc_rss_gb"  in metrics
    assert "cpu_pct"      in metrics


def test_sample_includes_vram_keys(monitor):
    """Verifies a sample always carries the VRAM keys, even without a GPU."""
    metrics = monitor.sample()

    assert "vram_used_gb" in metrics
    assert "vram_pct"     in metrics
    assert metrics["vram_used_gb"] >= 0.0


def test_sample_updates_peak(monitor):
    """Verifies sampling raises the RAM entries of the peak table above zero."""
    monitor.sample()

    assert monitor.peak["ram_used_gb"] > 0.0
    assert monitor.peak["ram_pct"]     > 0.0


def test_peak_is_monotonic_non_decreasing(monitor):
    """Verifies repeated sampling never lowers a recorded peak."""
    monitor.sample()
    first = monitor.peak["ram_used_gb"]
    monitor.sample()
    second = monitor.peak["ram_used_gb"]

    assert second >= first


def test_get_shm_usage_returns_tuple(monitor):
    """Verifies shared-memory usage is reported as gibibytes and a percentage."""
    used, pct = monitor._get_shm_usage()

    assert used >= 0.0
    assert 0.0 <= pct <= 100.0


def test_maybe_warn_respects_cooldown():
    """Verifies a second warning under the same key is suppressed inside the cooldown."""
    cfg    = FakeConfig(warn_cooldown_sec=1000.0)
    logger = CollectingLogger()
    m      = ResourceMonitor(cfg, logger=logger)

    m._maybe_warn("ram", "first")
    m._maybe_warn("ram", "second")

    assert logger.warnings == ["[ResourceMonitor] first"]


def test_maybe_warn_distinct_keys_both_fire():
    """Verifies warnings under different keys are not suppressed by each other."""
    cfg    = FakeConfig(warn_cooldown_sec=1000.0)
    logger = CollectingLogger()
    m      = ResourceMonitor(cfg, logger=logger)

    m._maybe_warn("ram", "a")
    m._maybe_warn("swap", "b")

    assert len(logger.warnings) == 2


def test_maybe_warn_after_cooldown_fires_again():
    """Verifies a zero cooldown lets consecutive warnings under one key both fire."""
    cfg    = FakeConfig(warn_cooldown_sec=0.0)
    logger = CollectingLogger()
    m      = ResourceMonitor(cfg, logger=logger)

    m._maybe_warn("ram", "a")
    m._maybe_warn("ram", "b")

    assert len(logger.warnings) == 2


def test_check_warnings_triggers_on_low_thresholds():
    """Verifies sampling emits a RAM warning once the threshold is set to zero."""
    cfg    = FakeConfig(warn_ram_pct=0.0, warn_swap_pct=0.0, warn_shm_pct=0.0, warn_cooldown_sec=1000.0)
    logger = CollectingLogger()
    m      = ResourceMonitor(cfg, logger=logger)

    metrics = m.sample()

    assert any("RAM usage" in w for w in logger.warnings)


def test_check_warnings_silent_with_high_thresholds():
    """Verifies sampling stays silent while every threshold is unreachable."""
    cfg    = FakeConfig(warn_ram_pct=999.0, warn_swap_pct=999.0, warn_shm_pct=999.0, warn_vram_pct=999.0)
    logger = CollectingLogger()
    m      = ResourceMonitor(cfg, logger=logger)

    m.sample()

    assert logger.warnings == []


def test_disabled_start_does_not_spawn_thread():
    """Verifies a disabled monitor logs the fact and starts no sampling thread."""
    cfg    = FakeConfig(enabled=False)
    logger = CollectingLogger()
    m      = ResourceMonitor(cfg, logger=logger)
    m.start()

    assert m._thread is None
    assert any("disabled" in s for s in logger.subsections)

    m.stop()


def test_start_stop_runs_sampling_thread():
    """Verifies start runs a sampling thread that publishes to the tracker and stop joins it."""
    cfg     = FakeConfig(poll_interval_sec=0.02)
    tracker = RecordingTracker()
    logger  = CollectingLogger()
    m       = ResourceMonitor(cfg, logger=logger, tracker=tracker, step_getter=lambda: 7)

    m.start()

    assert m._thread is not None
    assert m._thread.is_alive()

    deadline = time.time() + 3.0
    while m._sample_idx == 0 and time.time() < deadline:
        time.sleep(0.02)

    m.stop()

    assert m._thread is None
    assert m._sample_idx > 0
    assert len(tracker.calls) > 0


def test_publish_logs_to_tracker_with_step():
    """Verifies published metrics reach the tracker under the system prefix at the current step."""
    cfg     = FakeConfig()
    tracker = RecordingTracker()
    m       = ResourceMonitor(cfg, logger=None, tracker=tracker, step_getter=lambda: 42)

    m._publish({"ram_pct": 12.0})

    assert tracker.calls == [("system", {"ram_pct": 12.0}, 42)]


def test_publish_filters_to_tb_whitelist():
    """Verifies only whitelisted metric keys are forwarded to the tracker."""
    cfg     = FakeConfig()
    tracker = RecordingTracker()
    m       = ResourceMonitor(cfg, logger=None, tracker=tracker, step_getter=lambda: 3)

    m._publish({"ram_pct": 12.0, "ram_total_gb": 64.0, "vram_pct": 50.0, "proc_num_threads": 8.0, "loadavg_1m": 1.0})

    assert tracker.calls == [("system", {"ram_pct": 12.0}, 3)]


def test_publish_skipped_when_tb_disabled():
    """Verifies nothing is published when TensorBoard logging is switched off."""
    cfg     = FakeConfig(log_to_tensorboard=False)
    tracker = RecordingTracker()
    m       = ResourceMonitor(cfg, logger=None, tracker=tracker)

    m._publish({"ram_pct": 1.0})

    assert tracker.calls == []


def test_publish_skipped_without_tracker():
    """Verifies publishing without a tracker is a no-op rather than an error."""
    cfg = FakeConfig()
    m   = ResourceMonitor(cfg, logger=None, tracker=None)

    m._publish({"ram_pct": 1.0})


def test_start_logs_startup_info():
    """Verifies start logs a monitor section and an NVML availability table."""
    logger = CollectingLogger()
    m      = ResourceMonitor(FakeConfig(poll_interval_sec=0.02), logger=logger)
    m.start()
    m.stop()

    assert any("Resource Monitor" in s for s in logger.sections)
    assert any("NVML available" in table for table in logger.kv_tables)


def test_stop_logs_peak_metrics():
    """Verifies stop logs the peak section and the total sample count."""
    logger = CollectingLogger()
    m      = ResourceMonitor(FakeConfig(poll_interval_sec=0.02), logger=logger)
    m.sample()
    m.start()
    m.stop()

    assert any("Peaks" in s for s in logger.sections)
    assert any("Total samples" in table for table in logger.kv_tables)


def test_stop_without_start_is_safe():
    """Verifies stopping a monitor that never started leaves no thread behind."""
    m = ResourceMonitor(FakeConfig(), logger=CollectingLogger())
    m.stop()

    assert m._thread is None


def test_context_manager_starts_and_stops():
    """Verifies context-manager use starts the thread, samples, and joins on exit."""
    cfg     = FakeConfig(poll_interval_sec=0.02)
    tracker = RecordingTracker()

    with ResourceMonitor(cfg, logger=CollectingLogger(), tracker=tracker) as m:
        assert m._thread is not None
        deadline = time.time() + 3.0
        while m._sample_idx == 0 and time.time() < deadline:
            time.sleep(0.02)

    assert m._thread is None
    assert m._sample_idx > 0


def test_run_survives_sample_exception(monkeypatch):
    """Verifies a raising sample is reported as a warning without killing the thread."""
    cfg    = FakeConfig(poll_interval_sec=0.02)
    logger = CollectingLogger()
    m      = ResourceMonitor(cfg, logger=logger)

    def boom():
        raise ValueError("sample blew up")

    monkeypatch.setattr(m, "sample", boom)

    m.start()
    deadline = time.time() + 2.0
    while not logger.warnings and time.time() < deadline:
        time.sleep(0.02)
    m.stop()

    assert any("sample failed" in w for w in logger.warnings)


def test_nvml_unavailable_path_has_no_gpu_handles(monkeypatch):
    """Verifies a failed NVML init leaves no GPU handles and zeroed VRAM metrics."""
    def fail_init():
        raise RuntimeError("no nvml")

    monkeypatch.setattr(rm.pynvml, "nvmlInit", fail_init)

    m = ResourceMonitor(FakeConfig(), logger=CollectingLogger())

    assert m._nvml_ok     is False
    assert m._gpu_handles == []

    metrics = m.sample()

    assert metrics["vram_used_gb"] == 0.0
    assert metrics["vram_pct"]     == 0.0


def test_handles_cover_only_the_visible_devices(monkeypatch):
    """Verifies CUDA_VISIBLE_DEVICES restricts the NVML handles to the selected index."""
    requested = []

    monkeypatch.setattr(rm.pynvml, "nvmlInit", lambda: None)
    monkeypatch.setattr(rm.pynvml, "nvmlDeviceGetCount", lambda: 4)
    monkeypatch.setattr(rm.pynvml, "nvmlDeviceGetHandleByIndex", lambda index: requested.append(index) or f"handle{index}")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "2")

    m = ResourceMonitor(FakeConfig(), logger=CollectingLogger())

    assert m._nvml_ok     is True
    assert requested      == [2]
    assert m._gpu_handles == ["handle2"]


def test_handles_cover_every_device_when_no_selection_is_set(monkeypatch):
    """Verifies every device is handled when CUDA_VISIBLE_DEVICES is unset."""
    monkeypatch.setattr(rm.pynvml, "nvmlInit", lambda: None)
    monkeypatch.setattr(rm.pynvml, "nvmlDeviceGetCount", lambda: 3)
    monkeypatch.setattr(rm.pynvml, "nvmlDeviceGetHandleByIndex", lambda index: f"handle{index}")
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)

    m = ResourceMonitor(FakeConfig(), logger=CollectingLogger())

    assert m._gpu_handles == ["handle0", "handle1", "handle2"]


def test_uuid_device_selection_fails_loudly(monkeypatch):
    """Verifies a UUID-form CUDA_VISIBLE_DEVICES is rejected instead of guessed."""
    monkeypatch.setattr(rm.pynvml, "nvmlInit", lambda: None)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "GPU-8f2a1c")

    with pytest.raises(ValueError, match="CUDA_VISIBLE_DEVICES"):
        ResourceMonitor(FakeConfig(), logger=CollectingLogger())
