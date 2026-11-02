"""API routes for host monitoring, neighbour impact and server controls.

The system section serves the machine snapshot enriched with resource-watchdog,
neighbour-impact, detach and notification state, and exposes the process nuke, detach and
shutdown controls; the history sections serve the persisted GPU activity and
host telemetry and the server's own log; the impact section arms the
neighbour-impact monitor and sets the launch politeness level.
"""

from __future__ import annotations

from contention_monitor import ContentionMonitor
from notifier           import JobNotifier
from process_manager    import ProcessManager, ProcessNuke, ServerDetacher
from resource_watchdog  import ResourceWatchdog
from routers.dispatch   import HttpExchange, RouteTable, SubRouter
from system_monitor     import SystemMonitor
from web_logger         import WebLogger


class SystemRouter(SubRouter):
    """Serves the host snapshot, the telemetry histories and the neighbour-impact, detach and notification controls.

    Attributes:
        system     : Host monitor producing the machine snapshot and owning the telemetry logs.
        watchdog   : Resource watchdog contributing the alert state.
        contention : Neighbour-impact monitor, owner of the politeness settings.
        detacher   : Server detach and shutdown controller.
        notifier   : Job notification configuration and test sender.
        nuke       : Process nuke that kills every owned job.
        processes  : Local process manager, whose queue the nuke also clears.
        logger     : Console logger whose in-memory ring backs the server-log view.
    """

    def __init__(self, system: SystemMonitor, watchdog: ResourceWatchdog, contention: ContentionMonitor, detacher: ServerDetacher, notifier: JobNotifier, nuke: ProcessNuke, processes: ProcessManager, logger: WebLogger) -> None:
        """Stores the monitoring and control services, then declares the routes."""
        self.system     = system
        self.watchdog   = watchdog
        self.contention = contention
        self.detacher   = detacher
        self.notifier   = notifier
        self.nuke       = nuke
        self.processes  = processes
        self.logger     = logger

        super().__init__(("/api/system", "/api/gpu-activity", "/api/host-history", "/api/server-log", "/api/impact", "/api/notify"))

    def declare(self, table: RouteTable) -> None:
        """Registers the system snapshot, history, server-log, impact and notification routes."""
        table.add("GET",  "/api/system",            self.snapshot)
        table.add("GET",  "/api/gpu-activity",      self.gpu_activity)
        table.add("GET",  "/api/host-history",      self.host_history)
        table.add("GET",  "/api/server-log",        self.server_log)
        table.add("POST", "/api/system/nuke",       self.nuke_everything)
        table.add("POST", "/api/system/detach",     self.detach)
        table.add("POST", "/api/system/shutdown",   self.shutdown)
        table.add("POST", "/api/impact/arm",        self.arm_impact)
        table.add("POST", "/api/impact/politeness", self.politeness)
        table.add("POST", "/api/notify/config",     self.notify_config)
        table.add("POST", "/api/notify/test",       self.notify_test)

    def snapshot(self, exchange: HttpExchange) -> None:
        """Answers with the host snapshot enriched with alert, impact, server and notify state."""
        payload           = self.system.snapshot()
        payload["alerts"] = self.watchdog.state()
        payload["impact"] = self.contention.state()
        payload["server"] = self.detacher.state()
        payload["notify"] = self.notifier.state()

        exchange.send_json(payload)

    def gpu_activity(self, exchange: HttpExchange) -> None:
        """Answers with the bucketed per-GPU occupancy over the requested day, week or month span."""
        exchange.send_json(self.system.activity.state(exchange.text("range", "day")))

    def host_history(self, exchange: HttpExchange) -> None:
        """Answers with the host telemetry over the requested hour, day, week or month span."""
        exchange.send_json(self.system.host_hist.state(exchange.text("range", "day")))

    def server_log(self, exchange: HttpExchange) -> None:
        """Answers with the newest lines of the server's own console log."""
        exchange.send_json({"lines": self.logger.recent(exchange.integer("limit", "200"))})

    def nuke_everything(self, exchange: HttpExchange) -> None:
        """Clears the launch queue and kills every process owned by the console."""
        self.processes.clear_queue()
        exchange.send_result(self.nuke.nuke())

    def detach(self, exchange: HttpExchange) -> None:
        """Detaches the console server from the current terminal."""
        exchange.send_result(self.detacher.detach(), 500)

    def shutdown(self, exchange: HttpExchange) -> None:
        """Force-kills every other console on this root, answers with the server state, then shuts this console down."""
        siblings = self.detacher.kill_siblings()
        exchange.send_json({"ok": True, "siblings": siblings, **self.detacher.state()})
        self.detacher.shutdown()

    def arm_impact(self, exchange: HttpExchange) -> None:
        """Arms or disarms the neighbour-impact monitor's automatic nuke."""
        exchange.send_json(self.contention.arm(bool(exchange.body.get("armed"))))

    def politeness(self, exchange: HttpExchange) -> None:
        """Sets the launch politeness level and the auto-throttle flag from the request body."""
        exchange.send_result(self.contention.politeness.configure(exchange.body or {}))

    def notify_config(self, exchange: HttpExchange) -> None:
        """Updates the job notification configuration from the request body."""
        exchange.send_result(self.notifier.configure(exchange.body or {}))

    def notify_test(self, exchange: HttpExchange) -> None:
        """Sends a test job notification through the configured channel."""
        exchange.send_result(self.notifier.test())
