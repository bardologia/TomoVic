"""API routes of the results-oriented console tabs.

Serves the results browser, the dataset and run pickers, the run leaderboard and
the TensorBoard-backed training curves.
"""

from __future__ import annotations

from dataset_browser  import DatasetBrowser
from results_browser  import ResultsBrowser
from routers.dispatch import HttpExchange, RouteTable, SubRouter
from run_leaderboard  import RunLeaderboard
from training_curves  import TrainingCurves


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
        table.add("GET", "/api/fs/datasets",     self.dataset_roots)
        table.add("GET", "/api/fs/runs",         self.runs)
        table.add("GET", "/api/fs/run_groups",   self.run_groups)
        table.add("GET", "/api/fs/param_trials", self.param_trials)
        table.add("GET", "/api/fs/params",       self.params)

    def dataset_roots(self, exchange: HttpExchange) -> None:
        """Answers with the datasets found under the requested base directory."""
        exchange.send_result(self.datasets.datasets(exchange.text("base")))

    def runs(self, exchange: HttpExchange) -> None:
        """Answers with the runs under the requested bases, optionally split into seed units."""
        exchange.send_result(self.datasets.runs(exchange.texts("base"), seed_units=exchange.text("units", "0") == "1"))

    def run_groups(self, exchange: HttpExchange) -> None:
        """Answers with the run directories grouped by their parent trial."""
        exchange.send_result(self.datasets.run_groups(exchange.texts("base")))

    def param_trials(self, exchange: HttpExchange) -> None:
        """Answers with the parameter-extraction trials under the requested base."""
        exchange.send_result(self.datasets.param_trials(exchange.text("base")))

    def params(self, exchange: HttpExchange) -> None:
        """Answers with the parameter runs belonging to one dataset."""
        exchange.send_result(self.datasets.params(exchange.text("dataset")))


class LeaderboardRouter(SubRouter):
    """Routes the /api/leaderboard endpoints onto the run leaderboard.

    Attributes:
        leaderboard: Run leaderboard answering the requests.
    """

    def __init__(self, leaderboard: RunLeaderboard) -> None:
        """Stores the run leaderboard and declares its routes."""
        self.leaderboard = leaderboard

        super().__init__(("/api/leaderboard",))

    def declare(self, table: RouteTable) -> None:
        """Registers the /api/leaderboard routes."""
        table.add("GET", "/api/leaderboard",        self.table_view)
        table.add("GET", "/api/leaderboard/trials", self.trials)
        table.add("GET", "/api/leaderboard/diff",   self.diff)

    def table_view(self, exchange: HttpExchange) -> None:
        """Answers with one row per inference result under the requested base."""
        exchange.send_result(self.leaderboard.table(exchange.text("base")))

    def trials(self, exchange: HttpExchange) -> None:
        """Answers with the seed-aggregated trial table under the requested base."""
        exchange.send_result(self.leaderboard.trials(exchange.text("base")))

    def diff(self, exchange: HttpExchange) -> None:
        """Answers with the metric and config diff of the selected runs."""
        exchange.send_result(self.leaderboard.diff(exchange.texts("run")), 404)


class CurvesRouter(SubRouter):
    """Routes the /api/curves endpoints onto the training-curve reader.

    Attributes:
        curves: Training curve service answering the requests.
    """

    def __init__(self, curves: TrainingCurves) -> None:
        """Stores the training curve service and declares its routes."""
        self.curves = curves

        super().__init__(("/api/curves",))

    def declare(self, table: RouteTable) -> None:
        """Registers the /api/curves routes."""
        table.add("GET", "/api/curves",      self.curves_view)
        table.add("GET", "/api/curves/runs", self.runs)

    def curves_view(self, exchange: HttpExchange) -> None:
        """Answers with the requested scalar tag's series for every selected run."""
        exchange.send_result(self.curves.curves(exchange.texts("run"), exchange.text("tag")))

    def runs(self, exchange: HttpExchange) -> None:
        """Answers with the runs holding TensorBoard scalars under the requested base."""
        exchange.send_result(self.curves.runs(exchange.text("base")))
