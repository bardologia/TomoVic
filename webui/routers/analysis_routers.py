"""API routes of the model-analysis console tabs.

Wires the Fit Lab, Microscope probe, model survey, triage board and A/B autopsy
services onto their HTTP endpoints.
"""

from __future__ import annotations

from ab_autopsy       import AbAutopsy
from fit_lab          import FitLab
from model_probe      import ModelProbe
from model_survey     import ModelSurvey
from routers.dispatch import HttpExchange, RouteTable, SubRouter
from triage_board     import TriageBoard


class FitLabRouter(SubRouter):
    """Routes the Fit Lab endpoints: dataset listing, loading, maps and Gaussian fits.

    Attributes:
        fitlab: Fit Lab service answering the requests.
    """

    def __init__(self, fitlab: FitLab) -> None:
        """Stores the Fit Lab service and declares its routes."""
        self.fitlab = fitlab

        super().__init__(("/api/fitlab",))

    def declare(self, table: RouteTable) -> None:
        """Registers the /api/fitlab routes."""
        table.add("GET",  "/api/fitlab/datasets",   self.datasets)
        table.add("GET",  "/api/fitlab/status",     self.status)
        table.add("GET",  "/api/fitlab/map",        self.map_view)
        table.add("GET",  "/api/fitlab/fit_status", self.fit_status)
        table.add("GET",  "/api/fitlab/fit_result", self.fit_result)
        table.add("POST", "/api/fitlab/load",       self.load)
        table.add("POST", "/api/fitlab/fit",        self.fit)

    def datasets(self, exchange: HttpExchange) -> None:
        """Answers with the datasets discoverable under the requested base directory."""
        exchange.send_result(self.fitlab.datasets(exchange.text("base")))

    def status(self, exchange: HttpExchange) -> None:
        """Answers with the progress of the running dataset load."""
        exchange.send_json(self.fitlab.load_status())

    def map_view(self, exchange: HttpExchange) -> None:
        """Answers with the PNG overview map of the requested source layer."""
        exchange.send_png(self.fitlab.map_png(exchange.text("src", "slc")))

    def fit_status(self, exchange: HttpExchange) -> None:
        """Answers with the progress of the running Gaussian fit."""
        exchange.send_json(self.fitlab.fit_status())

    def fit_result(self, exchange: HttpExchange) -> None:
        """Answers with the finished fit result, or 404 while none exists."""
        exchange.send_result(self.fitlab.fit_result_payload(), 404)

    def load(self, exchange: HttpExchange) -> None:
        """Starts loading the dataset named in the request body."""
        exchange.send_result(self.fitlab.start_load(exchange.body.get("path", "")))

    def fit(self, exchange: HttpExchange) -> None:
        """Starts a Gaussian fit with the settings carried in the request body."""
        exchange.send_result(self.fitlab.start_fit(exchange.body))


class ProbeRouter(SubRouter):
    """Routes the Microscope endpoints for probing one loaded model on real pixels.

    Attributes:
        probe: Model probe service answering the requests.
    """

    def __init__(self, probe: ModelProbe) -> None:
        """Stores the model probe service and declares its routes."""
        self.probe = probe

        super().__init__(("/api/probe",))

    def declare(self, table: RouteTable) -> None:
        """Registers the /api/probe routes."""
        table.add("GET",  "/api/probe/runs",     self.runs)
        table.add("GET",  "/api/probe/status",   self.status)
        table.add("GET",  "/api/probe/layers",   self.layers)
        table.add("GET",  "/api/probe/map",      self.map_view)
        table.add("GET",  "/api/probe/features", self.features)
        table.add("GET",  "/api/probe/kernels",  self.kernels)
        table.add("POST", "/api/probe/load",        self.load)
        table.add("POST", "/api/probe/predict",     self.predict)
        table.add("POST", "/api/probe/fields",      self.fields)
        table.add("POST", "/api/probe/attribution", self.attribution)
        table.add("POST", "/api/probe/ablation",    self.ablation)
        table.add("POST", "/api/probe/occlusion",   self.occlusion)
        table.add("POST", "/api/probe/flips",       self.flips)
        table.add("POST", "/api/probe/whatif",      self.whatif)
        table.add("POST", "/api/probe/sweep",       self.sweep)
        table.add("POST", "/api/probe/vitals",      self.vitals)

    def runs(self, exchange: HttpExchange) -> None:
        """Answers with the probeable runs under the requested base directory."""
        exchange.send_result(self.probe.runs(exchange.text("base")))

    def status(self, exchange: HttpExchange) -> None:
        """Answers with the progress of the running model load."""
        exchange.send_json(self.probe.load_status())

    def layers(self, exchange: HttpExchange) -> None:
        """Answers with the layers of the loaded model that can be inspected."""
        exchange.send_result(self.probe.layers())

    def map_view(self, exchange: HttpExchange) -> None:
        """Answers with the PNG overview map of the loaded split region."""
        exchange.send_png(self.probe.map_png())

    def features(self, exchange: HttpExchange) -> None:
        """Answers with the PNG feature maps of one layer at the given azimuth/range pixel."""
        exchange.send_png(self.probe.features_png(exchange.integer("az"), exchange.integer("rg"), exchange.text("layer")))

    def kernels(self, exchange: HttpExchange) -> None:
        """Answers with the PNG kernel grid of one convolutional layer."""
        exchange.send_png(self.probe.kernels_png(exchange.text("layer")))

    def load(self, exchange: HttpExchange) -> None:
        """Starts loading the run, split and device named in the request body."""
        body = exchange.body
        exchange.send_result(self.probe.start_load(body.get("path", ""), body.get("split", "test"), body.get("device", "cpu")))

    def predict(self, exchange: HttpExchange) -> None:
        """Answers with the model prediction for the pixel described in the body."""
        exchange.send_result(self.probe.predict(exchange.body))

    def fields(self, exchange: HttpExchange) -> None:
        """Answers with the per-parameter field maps requested in the body."""
        exchange.send_result(self.probe.fields(exchange.body))

    def attribution(self, exchange: HttpExchange) -> None:
        """Answers with the input attribution of the prediction described in the body."""
        exchange.send_result(self.probe.attribution(exchange.body))

    def ablation(self, exchange: HttpExchange) -> None:
        """Answers with the prediction shift caused by the channel ablation in the body."""
        exchange.send_result(self.probe.ablation(exchange.body))

    def occlusion(self, exchange: HttpExchange) -> None:
        """Answers with the prediction shift caused by the occlusion window in the body."""
        exchange.send_result(self.probe.occlusion(exchange.body))

    def flips(self, exchange: HttpExchange) -> None:
        """Answers with the flip-consistency comparison for the pixel in the body."""
        exchange.send_result(self.probe.flips(exchange.body))

    def whatif(self, exchange: HttpExchange) -> None:
        """Answers with the prediction under the hand-edited inputs carried in the body."""
        exchange.send_result(self.probe.whatif(exchange.body))

    def sweep(self, exchange: HttpExchange) -> None:
        """Answers with the prediction sweep over the input range described in the body."""
        exchange.send_result(self.probe.sweep(exchange.body))

    def vitals(self, exchange: HttpExchange) -> None:
        """Answers with the activation vitals of the pixel described in the body."""
        exchange.send_result(self.probe.vitals(exchange.body))


class SurveyRouter(SubRouter):
    """Routes the model-survey endpoints that score many runs in one background pass.

    Attributes:
        survey: Model survey service answering the requests.
    """

    def __init__(self, survey: ModelSurvey) -> None:
        """Stores the model survey service and declares its routes."""
        self.survey = survey

        super().__init__(("/api/survey",))

    def declare(self, table: RouteTable) -> None:
        """Registers the /api/survey routes."""
        table.add("GET",  "/api/survey/runs",   self.runs)
        table.add("GET",  "/api/survey/status", self.status)
        table.add("GET",  "/api/survey/result", self.result)
        table.add("POST", "/api/survey/start",  self.start)
        table.add("POST", "/api/survey/cancel", self.cancel)

    def runs(self, exchange: HttpExchange) -> None:
        """Answers with the runs surveyable under the requested base directory."""
        exchange.send_result(self.survey.runs(exchange.text("base")))

    def status(self, exchange: HttpExchange) -> None:
        """Answers with the progress of the running survey."""
        exchange.send_json(self.survey.survey_status())

    def result(self, exchange: HttpExchange) -> None:
        """Answers with the finished survey result, or 404 while none exists."""
        exchange.send_result(self.survey.survey_result(), 404)

    def start(self, exchange: HttpExchange) -> None:
        """Starts a survey over the runs and settings carried in the request body."""
        exchange.send_result(self.survey.start(exchange.body))

    def cancel(self, exchange: HttpExchange) -> None:
        """Cancels the running survey."""
        exchange.send_result(self.survey.cancel())


class TriageRouter(SubRouter):
    """Routes the triage-board endpoints for reviewing the worst-scoring pixels of a cube.

    Attributes:
        triage: Triage board service answering the requests.
    """

    def __init__(self, triage: TriageBoard) -> None:
        """Stores the triage board service and declares its routes."""
        self.triage = triage

        super().__init__(("/api/triage",))

    def declare(self, table: RouteTable) -> None:
        """Registers the /api/triage routes."""
        table.add("GET",  "/api/triage/cases",    self.cases)
        table.add("GET",  "/api/triage/thumb",    self.thumb)
        table.add("GET",  "/api/triage/profile",  self.profile)
        table.add("POST", "/api/triage/annotate", self.annotate)

    def cases(self, exchange: HttpExchange) -> None:
        """Answers with the top-n triage cases of the requested cube."""
        result = self.triage.cases(
            cube_id = exchange.text("id"),
            top_n   = exchange.integer("n", "40"),
        )
        exchange.send_result(result)

    def thumb(self, exchange: HttpExchange) -> None:
        """Answers with the PNG thumbnail of the case anchored at the given pixel."""
        exchange.send_png(self.triage.thumb(exchange.text("id"), exchange.integer("az0"), exchange.integer("rg0")))

    def profile(self, exchange: HttpExchange) -> None:
        """Answers with the predicted and ground-truth profiles at the given pixel."""
        exchange.send_result(self.triage.profile(exchange.text("id"), exchange.integer("az"), exchange.integer("rg")))

    def annotate(self, exchange: HttpExchange) -> None:
        """Stores the case annotation carried in the request body."""
        exchange.send_result(self.triage.annotate(exchange.body))


class AutopsyRouter(SubRouter):
    """Routes the A/B autopsy endpoints comparing two runs pixel by pixel.

    Attributes:
        autopsy: A/B autopsy service answering the requests.
    """

    def __init__(self, autopsy: AbAutopsy) -> None:
        """Stores the A/B autopsy service and declares its routes."""
        self.autopsy = autopsy

        super().__init__(("/api/autopsy",))

    def declare(self, table: RouteTable) -> None:
        """Registers the /api/autopsy routes."""
        table.add("GET", "/api/autopsy/runs",    self.runs)
        table.add("GET", "/api/autopsy/compare", self.compare)
        table.add("GET", "/api/autopsy/profile", self.profile)

    def runs(self, exchange: HttpExchange) -> None:
        """Answers with the runs comparable under the requested base directory."""
        exchange.send_result(self.autopsy.runs(exchange.text("base")))

    def compare(self, exchange: HttpExchange) -> None:
        """Answers with the pixel-wise comparison of the two requested cubes."""
        result = self.autopsy.compare(
            a = exchange.text("a"),
            b = exchange.text("b"),
        )
        exchange.send_result(result)

    def profile(self, exchange: HttpExchange) -> None:
        """Answers with both runs' profiles at the given azimuth/range pixel."""
        result = self.autopsy.profile(
            a  = exchange.text("a"),
            b  = exchange.text("b"),
            az = exchange.integer("az"),
            rg = exchange.integer("rg"),
        )
        exchange.send_result(result)
