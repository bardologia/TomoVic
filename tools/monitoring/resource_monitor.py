"""Background sampler for host and GPU resource usage during a run.

Polls RAM, swap, /dev/shm, CPU, disk I/O and NVML GPU counters on a daemon
thread, mirrors a curated subset into TensorBoard through a tracker, warns when
configured thresholds are crossed, and reports peak usage at shutdown.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from pathlib  import Path

import psutil
import pynvml


class ResourceMonitor:
    """Samples system and GPU resource metrics on a background thread.

    Attributes:
        cfg: Resource-monitor configuration block supplying thresholds and interval.
        logger: Logger used for the startup table, warnings and the peak summary.
        tracker: Optional tracker that forwards scalars to TensorBoard.
        step_getter: Callable returning the training step to tag samples with.
        peak: Running maxima of memory and VRAM metrics observed so far.
    """

    TB_SCALARS      = ("ram_pct", "proc_rss_gb", "swap_pct", "shm_pct", "cpu_pct", "proc_cpu_pct", "disk_read_mb_s", "disk_write_mb_s")
    TB_GPU_SCALARS  = ("util_pct", "vram_pct", "temp_c", "power_w")

    def __init__(self, config, logger, tracker=None, step_getter=None):
        """Initializes the monitor and its NVML, disk and threading state.

        Args:
            config: Resource-monitor config with enabled, poll_interval_sec,
                log_to_tensorboard, the warn_*_pct thresholds and warn_cooldown_sec.
            logger: Logger for the startup table, threshold warnings and peaks.
            tracker: Optional tracker whose log_metrics receives the TensorBoard subset.
            step_getter: Callable returning the current step; defaults to a constant 0.
        """
        self.cfg         = config
        self.logger      = logger
        self.tracker     = tracker
        self.step_getter = step_getter or (lambda: 0)

        self._load_config()
        self._init_process()
        self._init_nvml()
        self._init_disk_tracking()
        self._init_threading()
        self._init_peak_tracking()

    def _load_config(self):
        """Copies the polling interval, thresholds and toggles out of the config."""
        self.enabled         = bool(self.cfg.enabled)
        self.interval        = float(self.cfg.poll_interval_sec)
        self.log_to_tb       = bool(self.cfg.log_to_tensorboard)
        self.warn_ram_pct    = float(self.cfg.warn_ram_pct)
        self.warn_vram_pct   = float(self.cfg.warn_vram_pct)
        self.warn_swap_pct   = float(self.cfg.warn_swap_pct)
        self.warn_shm_pct    = float(self.cfg.warn_shm_pct)
        self.warn_cooldown_s = float(self.cfg.warn_cooldown_sec)

    def _init_process(self):
        """Binds this process handle and primes the CPU-percent counters."""
        self.process = psutil.Process(os.getpid())
        self.process.cpu_percent(None)
        psutil.cpu_percent(None, percpu=False)

    def _init_nvml(self):
        """Opens NVML handles for the visible devices, leaving GPU sampling off on failure."""
        self._nvml_ok     = False
        self._gpu_handles = []
        selected          = self._visible_indices()

        try:
            pynvml.nvmlInit()
            indices           = range(pynvml.nvmlDeviceGetCount()) if selected is None else selected
            self._gpu_handles = [pynvml.nvmlDeviceGetHandleByIndex(i) for i in indices]
            self._nvml_ok     = True
        except Exception:
            pass

    @staticmethod
    def _visible_indices():
        """Returns the device indices named by CUDA_VISIBLE_DEVICES, or None when unset.

        Returns:
            List of non-negative device indices, or None when the variable is absent.

        Raises:
            ValueError: If the variable names devices by UUID or MIG identifier
                instead of plain integer indices.
        """
        raw = os.environ.get("CUDA_VISIBLE_DEVICES")
        if raw is None:
            return None

        tokens = [token.strip() for token in raw.split(",") if token.strip()]
        if not all(token.isdigit() for token in tokens):
            raise ValueError(f"CUDA_VISIBLE_DEVICES='{raw}' names devices by UUID or MIG identifier; ResourceMonitor needs plain device indices to attribute VRAM to this run")

        return [int(token) for token in tokens]

    def _init_disk_tracking(self):
        """Records the baseline disk I/O counters used for rate differencing."""
        self._last_disk_io = psutil.disk_io_counters()
        self._last_disk_t  = time.time()

    def _init_threading(self):
        """Creates the stop event, sample counter and per-kind warning timestamps."""
        self._stop_evt    = threading.Event()
        self._thread      = None
        self._sample_idx  = 0
        self._last_warn_t = {}

    def _init_peak_tracking(self):
        """Zeroes the peak table for the memory and VRAM metrics that are tracked."""
        self.peak = {
            "ram_used_gb"  : 0.0,
            "ram_pct"      : 0.0,
            "proc_rss_gb"  : 0.0,
            "swap_used_gb" : 0.0,
            "shm_used_gb"  : 0.0,
            "vram_used_gb" : 0.0,
            "vram_pct"     : 0.0,
        }

    @staticmethod
    def _bytes_to_gb(x):
        """Returns the byte count converted to gibibytes."""
        return float(x) / (1024.0 ** 3)

    def _get_shm_usage(self):
        """Returns the (used GB, percent) of /dev/shm, or zeros when it is unreadable."""
        try:
            usage = psutil.disk_usage("/dev/shm")
            return self._bytes_to_gb(usage.used), float(usage.percent)
        except (FileNotFoundError, PermissionError, OSError):
            return 0.0, 0.0

    def _maybe_warn(self, key, message):
        """Logs a warning for the given kind unless its cooldown has not yet elapsed."""
        now  = time.time()
        last = self._last_warn_t.get(key, 0.0)
        if now - last < self.warn_cooldown_s:
            return
        self._last_warn_t[key] = now
        if self.logger is not None:
            self.logger.warning(f"[ResourceMonitor] {message}")

    def _sample_ram_metrics(self, metrics):
        """Writes used, available and total system RAM in GB plus the percentage."""
        vm = psutil.virtual_memory()
        metrics["ram_used_gb"]      = self._bytes_to_gb(vm.used)
        metrics["ram_available_gb"] = self._bytes_to_gb(vm.available)
        metrics["ram_total_gb"]     = self._bytes_to_gb(vm.total)
        metrics["ram_pct"]          = float(vm.percent)

    def _sample_swap_metrics(self, metrics):
        """Writes swap usage in GB and percent."""
        sm = psutil.swap_memory()
        metrics["swap_used_gb"] = self._bytes_to_gb(sm.used)
        metrics["swap_pct"]     = float(sm.percent)

    def _sample_process_memory_metrics(self, metrics):
        """Writes this process's RSS, VMS and, when permitted, USS and shared memory in GB."""
        try:
            mi = self.process.memory_full_info()
            metrics["proc_rss_gb"]    = self._bytes_to_gb(mi.rss)
            metrics["proc_vms_gb"]    = self._bytes_to_gb(mi.vms)
            metrics["proc_uss_gb"]    = self._bytes_to_gb(getattr(mi, "uss", 0))
            metrics["proc_shared_gb"] = self._bytes_to_gb(getattr(mi, "shared", 0))
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            mi = self.process.memory_info()
            metrics["proc_rss_gb"] = self._bytes_to_gb(mi.rss)
            metrics["proc_vms_gb"] = self._bytes_to_gb(mi.vms)

    def _sample_process_stats(self, metrics):
        """Writes the thread and file-descriptor counts of this process when readable."""
        try:
            metrics["proc_num_threads"] = float(self.process.num_threads())
            metrics["proc_num_fds"]     = float(self.process.num_fds())
        except (psutil.AccessDenied, AttributeError):
            pass

    def _sample_process_children(self, metrics):
        """Writes the number of descendant processes and their summed RSS in GB."""
        try:
            children = self.process.children(recursive=True)
            metrics["proc_num_children"] = float(len(children))
            child_rss = 0
            for c in children:
                try:
                    child_rss += c.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            metrics["proc_children_rss_gb"] = self._bytes_to_gb(child_rss)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass

    def _sample_cpu_metrics(self, metrics):
        """Writes system and process CPU percentages plus the 1/5/15 minute load averages."""
        metrics["cpu_pct"]      = float(psutil.cpu_percent(None, percpu=False))
        metrics["proc_cpu_pct"] = float(self.process.cpu_percent(None))
        try:
            la1, la5, la15 = os.getloadavg()
            metrics["loadavg_1m"]  = float(la1)
            metrics["loadavg_5m"]  = float(la5)
            metrics["loadavg_15m"] = float(la15)
        except (AttributeError, OSError):
            pass

    def _sample_shm_metrics(self, metrics):
        """Writes /dev/shm usage in GB and percent."""
        shm_used_gb, shm_pct = self._get_shm_usage()
        metrics["shm_used_gb"] = shm_used_gb
        metrics["shm_pct"]     = shm_pct

    def _sample_disk_io_metrics(self, metrics):
        """Writes disk read and write throughput in MB/s since the previous sample."""
        now = time.time()
        try:
            io = psutil.disk_io_counters()
            dt = max(now - self._last_disk_t, 1e-6)
            if io is not None and self._last_disk_io is not None:
                metrics["disk_read_mb_s"]  = (io.read_bytes - self._last_disk_io.read_bytes) / dt / (1024.0 ** 2)
                metrics["disk_write_mb_s"] = (io.write_bytes - self._last_disk_io.write_bytes) / dt / (1024.0 ** 2)
            self._last_disk_io = io
            self._last_disk_t  = now
        except (PermissionError, OSError):
            pass

    def _sample_gpu_nvml_metrics(self, metrics):
        """Writes per-device VRAM, utilization, temperature and power, and returns the totals.

        Args:
            metrics: Metric dictionary to populate with gpu{i}_* entries.

        Returns:
            Tuple of (used GB, total GB) summed over the visible devices.
        """
        gpu_total = 0.0
        gpu_used  = 0.0
        
        if self._nvml_ok:
            for i, h in enumerate(self._gpu_handles):
                try:
                    mem      = pynvml.nvmlDeviceGetMemoryInfo(h)
                    util     = pynvml.nvmlDeviceGetUtilizationRates(h)
                    used_gb  = self._bytes_to_gb(mem.used)
                    total_gb = self._bytes_to_gb(mem.total)
                    free_gb  = self._bytes_to_gb(mem.free)
                    pct      = 100.0 * mem.used / max(mem.total, 1)
                    
                    metrics[f"gpu{i}_vram_used_gb"]  = used_gb
                    metrics[f"gpu{i}_vram_free_gb"]  = free_gb
                    metrics[f"gpu{i}_vram_total_gb"] = total_gb
                    metrics[f"gpu{i}_vram_pct"]      = pct
                    metrics[f"gpu{i}_util_pct"]      = float(util.gpu)
                    metrics[f"gpu{i}_mem_util_pct"]  = float(util.memory)
                    
                    try:
                        temp = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
                        metrics[f"gpu{i}_temp_c"] = float(temp)
                    except Exception:
                        pass
                    
                    try:
                        power = pynvml.nvmlDeviceGetPowerUsage(h) / 1000.0
                        metrics[f"gpu{i}_power_w"] = float(power)
                    except Exception:
                        pass
                    
                    gpu_total += total_gb
                    gpu_used += used_gb
                except Exception:
                    continue
        
        return gpu_used, gpu_total

    def _update_peak_metrics(self, metrics):
        """Raises each tracked peak to the value seen in this sample."""
        for k in list(self.peak.keys()):
            if k in metrics and metrics[k] > self.peak[k]:
                self.peak[k] = float(metrics[k])

    def _check_warnings(self, metrics, gpu_used, gpu_total):
        """Emits cooldown-gated warnings for RAM, aggregated VRAM, swap and /dev/shm.

        Args:
            metrics: Metric dictionary produced by the sampling helpers.
            gpu_used: VRAM in use across the visible devices, in GB.
            gpu_total: Total VRAM across the visible devices, in GB.
        """
        if metrics["ram_pct"] >= self.warn_ram_pct:
            self._maybe_warn(
                "ram",
                f"RAM usage {metrics['ram_pct']:.1f}% "
                f"({metrics['ram_used_gb']:.2f}/{metrics['ram_total_gb']:.2f} GB) "
                f">= threshold {self.warn_ram_pct:.1f}% "
                f"(proc RSS {metrics.get('proc_rss_gb', 0):.2f} GB, "
                f"shm {metrics['shm_used_gb']:.2f} GB)",
            )
        
        vram_pct = (100.0 * gpu_used / gpu_total) if gpu_total > 0 else 0.0
        if vram_pct >= self.warn_vram_pct and gpu_total > 0:
            self._maybe_warn(
                "vram",
                f"VRAM usage {vram_pct:.1f}% "
                f"({gpu_used:.2f}/{gpu_total:.2f} GB, aggregated over the {len(self._gpu_handles)} GPUs this run can see) "
                f">= threshold {self.warn_vram_pct:.1f}%",
            )
        
        if metrics["swap_pct"] >= self.warn_swap_pct:
            self._maybe_warn(
                "swap",
                f"Swap usage {metrics['swap_pct']:.1f}% "
                f"({metrics['swap_used_gb']:.2f} GB) >= threshold {self.warn_swap_pct:.1f}%",
            )
        
        if metrics["shm_pct"] >= self.warn_shm_pct:
            self._maybe_warn(
                "shm",
                f"/dev/shm usage {metrics['shm_pct']:.1f}% ({metrics['shm_used_gb']:.2f} GB) "
                f">= threshold {self.warn_shm_pct:.1f}% "
                f"(DataLoader workers may exhaust shared memory)",
            )

    def sample(self):
        """Collects one full resource snapshot, updating peaks and firing warnings.

        Returns:
            Mapping of metric name to float value covering RAM, swap, process
            memory, CPU, /dev/shm, disk throughput and per-GPU counters, plus the
            aggregated vram_used_gb and vram_pct.
        """
        metrics = {}

        self._sample_ram_metrics(metrics)
        self._sample_swap_metrics(metrics)
        self._sample_process_memory_metrics(metrics)
        self._sample_process_stats(metrics)
        self._sample_process_children(metrics)
        self._sample_cpu_metrics(metrics)
        self._sample_shm_metrics(metrics)
        self._sample_disk_io_metrics(metrics)
        
        gpu_used, gpu_total = self._sample_gpu_nvml_metrics(metrics)

        vram_pct_overall = (100.0 * gpu_used / gpu_total) if gpu_total > 0 else 0.0
        metrics["vram_used_gb"] = gpu_used
        metrics["vram_pct"]     = vram_pct_overall

        self._update_peak_metrics(metrics)
        self._check_warnings(metrics, gpu_used, gpu_total)
        self._sample_idx += 1

        return metrics

    def _tb_metrics(self, metrics):
        """Returns the subset of metrics allowed onto TensorBoard."""
        allowed = set(self.TB_SCALARS)
        for i in range(len(self._gpu_handles)):
            allowed.update(f"gpu{i}_{suffix}" for suffix in self.TB_GPU_SCALARS)

        return {k: v for k, v in metrics.items() if k in allowed}

    def _publish(self, metrics):
        """Logs the TensorBoard subset under the 'system' prefix at the current step."""
        step = int(self.step_getter() or 0)
        if self.log_to_tb and self.tracker is not None:
            self.tracker.log_metrics("system", self._tb_metrics(metrics), step)

    def _run(self):
        """Samples and publishes on the poll interval until the stop event is set."""
        while not self._stop_evt.is_set():
            try:
                metrics = self.sample()
                self._publish(metrics)
            except Exception as exc:
                if self.logger is not None:
                    self.logger.warning(f"[ResourceMonitor] sample failed: {exc}")
            self._stop_evt.wait(self.interval)

    def _log_startup_info(self):
        """Logs the monitor's interval, NVML status, TensorBoard wiring and thresholds."""
        if self.logger is None:
            return
        
        tb_effective = self.log_to_tb and self.tracker is not None and getattr(self.tracker, "writer", None) is not None

        self.logger.section("[Resource Monitor]")
        self.logger.kv_table({
            "Enabled"         : self.enabled,
            "Poll interval"   : f"{self.interval:.1f} s",
            "NVML available"  : f"{self._nvml_ok} ({len(self._gpu_handles)} GPUs; VRAM figures aggregate the devices named by CUDA_VISIBLE_DEVICES, gpu0 being this run's cuda:0)",
            "TB logging"      : f"{self.log_to_tb} (effective: {tb_effective})",
            "Warn thresholds" : f"RAM>={self.warn_ram_pct:g}%  VRAM>={self.warn_vram_pct:g}%  SWAP>={self.warn_swap_pct:g}%  SHM>={self.warn_shm_pct:g}%",
            "Warn cooldown"   : f"{self.warn_cooldown_s:g} s per warning kind",
        })

    def start(self):
        """Starts the daemon sampling thread, or returns immediately when disabled."""
        if not self.enabled:
            if self.logger is not None:
                self.logger.subsection("[ResourceMonitor] disabled by config")
            return
        
        if self._thread is not None and self._thread.is_alive():
            return

        self._log_startup_info()

        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._run, name="ResourceMonitor", daemon=True)
        self._thread.start()

    def _log_peak_metrics(self):
        """Logs the peak memory and VRAM figures together with the sample count."""
        if self.logger is None:
            return

        if self._sample_idx == 0:
            return

        peaks = {}
        for key, value in self.peak.items():
            unit                 = "%" if key.endswith("_pct") else "GB"
            peaks[f"peak {key}"] = f"{value:.2f} {unit}"
        peaks["Total samples"] = self._sample_idx

        self.logger.section("[Resource Monitor - Peaks]")
        self.logger.subsection(f"VRAM peaks aggregate the {len(self._gpu_handles)} GPUs this run can see, and every process on them, not only this run's allocations.")
        self.logger.kv_table(peaks)

    def _stop_thread(self):
        """Signals the sampling thread and joins it with a bounded timeout."""
        if self._thread is None:
            return
        
        self._stop_evt.set()
        self._thread.join(timeout=max(self.interval * 2, 5.0))
        self._thread = None

    def stop(self):
        """Stops sampling, logs the peak summary and shuts NVML down."""
        self._stop_thread()
        self._log_peak_metrics()
        self._shutdown_nvml()

    def _shutdown_nvml(self):
        """Releases the NVML session if one was successfully opened."""
        if self._nvml_ok:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass
            self._nvml_ok = False

    def __enter__(self):
        """Starts monitoring and returns this monitor for use as a context manager."""
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        """Stops monitoring on context exit and never suppresses the exception."""
        self.stop()
        return False
