"""API routes for host monitoring and server controls.

The system section serves the machine snapshot enriched with detach and
notification state, and exposes the process nuke, detach and shutdown controls.
"""

from __future__ import annotations

from notifier         import JobNotifier
from process_manager  import ProcessManager, ProcessNuke, ServerDetacher
from routers.dispatch import HttpExchange, RouteTable, SubRouter
from system_monitor   import SystemMonitor


class SystemRouter(SubRouter):
    """Serves the host snapshot and the detach and notification controls.

    Attributes:
        system: Host monitor producing the machine snapshot.
        detacher: Server detach and shutdown controller.
        notifier: Job notification configuration and test sender.
        nuke: Process nuke that kills every owned job.
        processes: Local process manager, whose queue the nuke also clears.
    """

    def __init__(self, system: SystemMonitor, detacher: ServerDetacher, notifier: JobNotifier, nuke: ProcessNuke, processes: ProcessManager) -> None:
        """Stores the monitoring and control services, then declares the routes."""
        self.system    = system
        self.detacher  = detacher
        self.notifier  = notifier
        self.nuke      = nuke
        self.processes = processes

        super().__init__(("/api/system", "/api/notify"))

    def declare(self, table: RouteTable) -> None:
        """Registers the system snapshot and notification routes."""
        table.add("GET",  "/api/system",          self.snapshot)
        table.add("POST", "/api/system/nuke",     self.nuke_everything)
        table.add("POST", "/api/system/detach",   self.detach)
        table.add("POST", "/api/system/shutdown", self.shutdown)
        table.add("POST", "/api/notify/config",   self.notify_config)
        table.add("POST", "/api/notify/test",     self.notify_test)

    def snapshot(self, exchange: HttpExchange) -> None:
        """Answers with the host snapshot enriched with server and notify state."""
        payload           = self.system.snapshot()
        payload["server"] = self.detacher.state()
        payload["notify"] = self.notifier.state()

        exchange.send_json(payload)

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

    def notify_config(self, exchange: HttpExchange) -> None:
        """Updates the job notification configuration from the request body."""
        exchange.send_result(self.notifier.configure(exchange.body or {}))

    def notify_test(self, exchange: HttpExchange) -> None:
        """Sends a test job notification through the configured channel."""
        exchange.send_result(self.notifier.test())
