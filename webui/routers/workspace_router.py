"""API routes of the dataset bridge (/api/workspace).

Answers the current dataset (with what a TomoVis window holds and whether it
should open the current dataset), the list of registered datasets with their
Cube strip entries, one dataset's payload, and sets the current dataset from a
TomoVic page. The payloads are described in webui/tomovis/README.md and in the
bridge package.
"""

from __future__ import annotations

from bridge.dataset_bridge import BridgeRefusal, DatasetBridge
from routers.dispatch      import HttpExchange, RouteTable, SubRouter


class WorkspaceRouter(SubRouter):
    """Routes /api/workspace onto the dataset bridge.

    Attributes:
        bridge : Dataset bridge answering the requests.
    """

    def __init__(self, bridge: DatasetBridge) -> None:
        """Stores the bridge and declares the routes.

        Args:
            bridge : Dataset bridge.
        """

        self.bridge = bridge

        super().__init__(("/api/workspace",))

    def declare(self, table: RouteTable) -> None:
        """Registers the /api/workspace routes."""

        table.add("GET",  "/api/workspace/current",  self.current)
        table.add("GET",  "/api/workspace/datasets", self.datasets)
        table.add("GET",  "/api/workspace/dataset",  self.dataset)
        table.add("POST", "/api/workspace/current",  self.use)

    def handle(self, exchange: HttpExchange) -> bool:
        """Refuses POST bodies that are not JSON objects with 400, then dispatches through the route table."""

        if exchange.method == "POST" and not isinstance(exchange.body, dict):
            exchange.send_json({"ok": False, "error": "the request body must be a JSON object"}, 400)
            return True
        return super().handle(exchange)

    def refuse(self, exchange: HttpExchange, refusal: BridgeRefusal) -> None:
        """Answers a refused request with {ok: false, error} (and the piece, when it concerns one) under its status."""

        payload = {"ok": False, "error": str(refusal)}
        if refusal.piece is not None:
            payload["piece"] = refusal.piece
        exchange.send_json(payload, refusal.status)

    def current(self, exchange: HttpExchange) -> None:
        """Answers the current dataset; with ``sid``, also what that TomoVis window holds and whether it should open the current dataset."""

        exchange.send_json(self.bridge.current_payload(exchange.text("sid") or None))

    def datasets(self, exchange: HttpExchange) -> None:
        """Answers every registered dataset, newest opened first."""

        exchange.send_json(self.bridge.datasets_payload(exchange.text("base")))

    def dataset(self, exchange: HttpExchange) -> None:
        """Answers one dataset's payload, 404 for an unknown id."""

        try:
            result = self.bridge.dataset_payload(exchange.text("id"))
        except BridgeRefusal as refusal:
            self.refuse(exchange, refusal)
            return
        exchange.send_result(result, 404)

    def use(self, exchange: HttpExchange) -> None:
        """Makes a dataset current from a TomoVic page; 400 for an id the console may not open."""

        dataset_id = exchange.body.get("id")
        if "id" not in exchange.body or not (dataset_id is None or isinstance(dataset_id, str)):
            exchange.send_json({"ok": False, "error": "id must be a dataset folder path or null"}, 400)
            return
        try:
            result = self.bridge.use(dataset_id)
        except BridgeRefusal as refusal:
            self.refuse(exchange, refusal)
            return
        exchange.send_json(result)
