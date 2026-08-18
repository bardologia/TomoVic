"""API routes for host monitoring, GPU policy and the Terrabyte cluster.

The system section serves the machine snapshot enriched with watchdog, GPU guard,
schedule, detach and notification state, and exposes the process nuke, detach and
shutdown controls; the Terrabyte section drives cluster submission, monitoring and
run pulling.
"""

from __future__ import annotations

from contention_monitor import ContentionMonitor
from gpu_schedule       import GpuSchedule
from gpu_watchdog       import GpuWatchdog
from notifier           import JobNotifier
from process_manager    import ProcessManager, ProcessNuke, ServerDetacher
from resource_watchdog  import ResourceWatchdog
from routers.dispatch   import HttpExchange, RouteTable, SubRouter
from system_monitor     import SystemMonitor
from terrabyte_console  import TerrabyteJobManager
from terrabyte_launcher import TerrabyteLauncher
from terrabyte_monitor  import TerrabyteMonitor, TerrabyteRunPuller


class SystemRouter(SubRouter):
    """Serves the host snapshot and the GPU policy, detach and notification controls.

    Attributes:
        system: Host monitor producing the machine snapshot.
        watchdog: Resource watchdog contributing the alert state.
        contention: Neighbour-impact monitor.
        gpu_guard: GPU intrusion watchdog.
        gpu_schedule: GPU time-window policy.
        detacher: Server detach and shutdown controller.
        notifier: Job notification configuration and test sender.
        nuke: Process nuke that kills every owned job.
        processes: Local process manager, whose queue the nuke also clears.
    """

    def __init__(self, system: SystemMonitor, watchdog: ResourceWatchdog, contention: ContentionMonitor, gpu_guard: GpuWatchdog, gpu_schedule: GpuSchedule, detacher: ServerDetacher, notifier: JobNotifier, nuke: ProcessNuke, processes: ProcessManager) -> None:
        """Stores the monitoring and policy services, then declares the routes."""
        self.system       = system
        self.watchdog     = watchdog
        self.contention   = contention
        self.gpu_guard    = gpu_guard
        self.gpu_schedule = gpu_schedule
        self.detacher     = detacher
        self.notifier     = notifier
        self.nuke         = nuke
        self.processes    = processes

        super().__init__(("/api/system", "/api/gpu-guard", "/api/gpu-schedule", "/api/impact", "/api/notify"))

    def declare(self, table: RouteTable) -> None:
        """Registers the system snapshot, GPU policy, impact and notification routes."""
        table.add("GET",  "/api/system",             self.snapshot)
        table.add("GET",  "/api/gpu-guard/history",  self.guard_history)
        table.add("POST", "/api/system/nuke",        self.nuke_everything)
        table.add("POST", "/api/system/detach",      self.detach)
        table.add("POST", "/api/system/shutdown",    self.shutdown)
        table.add("POST", "/api/gpu-schedule",       self.schedule)
        table.add("POST", "/api/impact/arm",         self.arm_impact)
        table.add("POST", "/api/notify/config",      self.notify_config)
        table.add("POST", "/api/notify/test",        self.notify_test)

    def snapshot(self, exchange: HttpExchange) -> None:
        """Answers with the host snapshot enriched with alert, GPU, server and notify state."""
        payload                 = self.system.snapshot()
        payload["alerts"]       = self.watchdog.state()
        payload["impact"]       = self.contention.state()
        payload["gpu_guard"]    = self.gpu_guard.state()
        payload["gpu_schedule"] = self.gpu_schedule.state()
        payload["server"]       = self.detacher.state()
        payload["notify"]       = self.notifier.state()

        exchange.send_json(payload)

    def guard_history(self, exchange: HttpExchange) -> None:
        """Answers with the most recent GPU-guard events, capped by the limit parameter."""
        exchange.send_json(self.gpu_guard.history(exchange.integer("limit", "100")))

    def nuke_everything(self, exchange: HttpExchange) -> None:
        """Clears the launch queue and kills every process owned by the console."""
        self.processes.clear_queue()
        exchange.send_result(self.nuke.nuke())

    def detach(self, exchange: HttpExchange) -> None:
        """Detaches the console server from the current terminal."""
        exchange.send_result(self.detacher.detach(), 500)

    def shutdown(self, exchange: HttpExchange) -> None:
        """Answers with the server state and then shuts the console down."""
        exchange.send_json({"ok": True, **self.detacher.state()})
        self.detacher.shutdown()

    def schedule(self, exchange: HttpExchange) -> None:
        """Updates the GPU time-window schedule from the request body."""
        exchange.send_result(self.gpu_schedule.update(exchange.body))

    def arm_impact(self, exchange: HttpExchange) -> None:
        """Arms or disarms the neighbour-impact monitor."""
        exchange.send_json(self.contention.arm(bool(exchange.body.get("armed"))))

    def notify_config(self, exchange: HttpExchange) -> None:
        """Updates the job notification configuration from the request body."""
        exchange.send_result(self.notifier.configure(exchange.body or {}))

    def notify_test(self, exchange: HttpExchange) -> None:
        """Sends a test job notification through the configured channel."""
        exchange.send_result(self.notifier.test())


class TerrabyteRouter(SubRouter):
    """Serves the Terrabyte cluster endpoints: monitoring, submission and run pulling.

    Attributes:
        monitor: Cluster monitor providing queue snapshots, logs, quota and cancellation.
        launcher: Cluster submitter building and sending the sbatch jobs.
        puller: Run puller mirroring finished cluster runs to the local runs root.
        console: Terrabyte job manager the launcher registers submitted jobs with.
    """

    def __init__(self, monitor: TerrabyteMonitor, launcher: TerrabyteLauncher, puller: TerrabyteRunPuller, console: TerrabyteJobManager) -> None:
        """Stores the cluster services and declares the routes."""
        self.monitor  = monitor
        self.launcher = launcher
        self.puller   = puller
        self.console  = console

        super().__init__(("/api/terrabyte",))

    def declare(self, table: RouteTable) -> None:
        """Registers the /api/terrabyte routes."""
        table.add("GET",  "/api/terrabyte",             self.snapshot)
        table.add("GET",  "/api/terrabyte/log",         self.log)
        table.add("GET",  "/api/terrabyte/quota",       self.quota)
        table.add("GET",  "/api/terrabyte/launch-info", self.launch_info)
        table.add("GET",  "/api/terrabyte/runs",        self.runs)
        table.add("GET",  "/api/terrabyte/pulls",       self.pulls)
        table.add("POST", "/api/terrabyte/launch",       self.launch)
        table.add("POST", "/api/terrabyte/cancel",       self.cancel)
        table.add("POST", "/api/terrabyte/cancel-all",   self.cancel_all)
        table.add("POST", "/api/terrabyte/pull",         self.pull)
        table.add("POST", "/api/terrabyte/pull-missing", self.pull_missing)
        table.add("POST", "/api/terrabyte/delete-runs",  self.delete_runs)
        table.add("POST", "/api/terrabyte/clean-home",   self.clean_home)
        table.add("POST", "/api/terrabyte/verify-pulls", self.verify_pulls)
        table.add("POST", "/api/terrabyte/auto-pull",    self.auto_pull)

    def snapshot(self, exchange: HttpExchange) -> None:
        """Answers with the cluster queue snapshot, refreshed when refresh=1 is passed."""
        exchange.send_json(self.monitor.snapshot(refresh=exchange.integer("refresh", "0") == 1))

    def log(self, exchange: HttpExchange) -> None:
        """Answers with the tail of one cluster job's log."""
        exchange.send_result(self.monitor.log_tail(exchange.text("job"), exchange.integer("lines", "200")))

    def quota(self, exchange: HttpExchange) -> None:
        """Answers with the cluster storage quota, refreshed when refresh=1 is passed."""
        exchange.send_json(self.monitor.quota(refresh=exchange.integer("refresh", "0") == 1))

    def cancel(self, exchange: HttpExchange) -> None:
        """Cancels the cluster job named in the request body."""
        exchange.send_result(self.monitor.cancel(str((exchange.body or {}).get("job_id", ""))))

    def cancel_all(self, exchange: HttpExchange) -> None:
        """Cancels every cluster job owned by the account."""
        exchange.send_result(self.monitor.cancel_all())

    def runs(self, exchange: HttpExchange) -> None:
        """Answers with the run directories present on the cluster and their pull state."""
        exchange.send_json(self.puller.list_runs())

    def pulls(self, exchange: HttpExchange) -> None:
        """Answers with the state of the running and finished run pulls."""
        exchange.send_json(self.puller.status())

    def pull(self, exchange: HttpExchange) -> None:
        """Pulls the single cluster run path named in the request body."""
        exchange.send_result(self.puller.pull(str((exchange.body or {}).get("rel", ""))))

    def pull_missing(self, exchange: HttpExchange) -> None:
        """Pulls every cluster run path listed in the request body."""
        exchange.send_result(self.puller.pull_batch((exchange.body or {}).get("rels") or []))

    def delete_runs(self, exchange: HttpExchange) -> None:
        """Deletes the listed run directories from the cluster."""
        exchange.send_result(self.puller.delete_runs((exchange.body or {}).get("rels") or []))

    def clean_home(self, exchange: HttpExchange) -> None:
        """Cleans the cluster home directory of stale job artifacts."""
        exchange.send_result(self.monitor.clean_home())

    def verify_pulls(self, exchange: HttpExchange) -> None:
        """Verifies that the listed runs were pulled completely."""
        exchange.send_result(self.puller.verify_pulls((exchange.body or {}).get("rels") or []))

    def auto_pull(self, exchange: HttpExchange) -> None:
        """Enables or disables automatic pulling of finished cluster runs."""
        exchange.send_result(self.puller.set_auto(bool((exchange.body or {}).get("enabled"))))

    def launch_info(self, exchange: HttpExchange) -> None:
        """Answers with the submittable entry points and default cluster resources."""
        exchange.send_json(self.launcher.info())

    def launch(self, exchange: HttpExchange) -> None:
        """Submits an entry point to the cluster, optionally as a sweep or a dry run."""
        body   = exchange.body or {}
        result = self.launcher.launch(
            self.console,
            script_key = body.get("script_key", ""),
            overrides  = body.get("overrides") or {},
            resources  = body.get("resources") or {},
            sweep      = bool(body.get("sweep")),
            dry_run    = bool(body.get("dry_run")),
            limit      = int(body.get("limit") or 0),
        )

        exchange.send_result(result)
