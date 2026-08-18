"""API routes of the results-oriented console tabs.

Serves the results browser and the dataset and run pickers.
"""

from __future__ import annotations

from dataset_browser  import DatasetBrowser
from results_browser  import ResultsBrowser
from routers.dispatch import HttpExchange, RouteTable, SubRouter


class ResultsRouter(SubRouter):
    """Routes the /api/results endpoints onto the results browser.

    Attributes:
        results: Results browser answering the requests.
    """

    def __init__(self, results: ResultsBrowser) -> None:
        """Stores the results browser and declares its routes."""
        self.results = results

        super().__init__(("/api/results",))

    def declare(self, table: RouteTable) -> None:
        """Registers the /api/results routes."""
        table.add("GET", "/api/results/tree",    self.tree)
        table.add("GET", "/api/results/folder",  self.folder)
        table.add("GET", "/api/results/catalog", self.catalog)
        table.add("GET", "/api/results/gallery", self.gallery)

    def tree(self, exchange: HttpExchange) -> None:
        """Answers with the file-count tree of the requested results root."""
        exchange.send_result(self.results.tree(exchange.text("path")), 404)

    def folder(self, exchange: HttpExchange) -> None:
        """Answers with the classified contents of one folder inside an opened root."""
        exchange.send_result(self.results.folder(exchange.text("root"), exchange.text("rel")), 404)

    def catalog(self, exchange: HttpExchange) -> None:
        """Answers with the dataset and run catalogs of the requested roots."""
        exchange.send_json(self.results.catalog(exchange.text("datasets"), exchange.text("logs")))

    def gallery(self, exchange: HttpExchange) -> None:
        """Answers with every image and animation under the requested root."""
        exchange.send_result(self.results.gallery(exchange.text("root")), 404)


class DatasetRouter(SubRouter):
    """Routes the /api/fs endpoints onto the dataset and run browser.

    Attributes:
        datasets: Dataset browser answering the requests.
    """

    def __init__(self, datasets: DatasetBrowser) -> None:
        """Stores the dataset browser and declares its routes."""
        self.datasets = datasets

        super().__init__(("/api/fs",))

    def declare(self, table: RouteTable) -> None:
        """Registers the /api/fs routes."""
        table.add("GET", "/api/fs/datasets",   self.dataset_roots)
        table.add("GET", "/api/fs/runs",       self.runs)
        table.add("GET", "/api/fs/run_groups", self.run_groups)

    def dataset_roots(self, exchange: HttpExchange) -> None:
        """Answers with the datasets found under the requested base directory."""
        exchange.send_result(self.datasets.datasets(exchange.text("base")))

    def runs(self, exchange: HttpExchange) -> None:
        """Answers with the runs under the requested bases, optionally split into seed units."""
        exchange.send_result(self.datasets.runs(exchange.texts("base"), seed_units=exchange.text("units", "0") == "1"))

    def run_groups(self, exchange: HttpExchange) -> None:
        """Answers with the run directories grouped by their parent trial."""
        exchange.send_result(self.datasets.run_groups(exchange.texts("base")))
