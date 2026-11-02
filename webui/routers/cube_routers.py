"""API routes of the Cube Explorer and slice-collector tabs.

Exposes preprocessing-run listing and loading, parameter-run listing and the
per-pixel Gaussian readout of the parametrized tomogram, plane/slice/transect
renderings, colour bars, point clouds for the 3D and globe views, the DEM grid,
per-pass SLC amplitude and interferogram phase maps, Pauli decomposition maps,
pixel readouts, scene summaries and the north-up globe drape, the run's saved
figures, and multi-run slice collection with its basket mailer.
"""

from __future__ import annotations

from cube_explorer    import CubeExplorer, SliceCollectionMailer, SliceCollector
from routers.dispatch import HttpExchange, RouteTable, SubRouter


class CubeRouter(SubRouter):
    """Routes the /api/cubes endpoints onto the cube explorer service.

    Attributes:
        STRETCHES : Accepted values of the Pauli ``stretch`` query parameter.
        cubes     : Cube explorer service answering the requests.
    """

    STRETCHES = ("channel", "shared")

    def __init__(self, cubes: CubeExplorer) -> None:
        """Stores the cube explorer service and declares its routes."""
        self.cubes = cubes

        super().__init__(("/api/cubes",))

    def _shared_stretch(self, exchange: HttpExchange) -> bool:
        """Returns whether the Pauli stretch pools every component; an absent parameter means per channel, like both views.

        Raises:
            ValueError : If the parameter is neither "channel" nor "shared".
        """
        stretch = exchange.text("stretch", "channel")
        if stretch not in self.STRETCHES:
            raise ValueError(f"stretch must be one of {self.STRETCHES}, got {stretch!r}")

        return stretch == "shared"

    def declare(self, table: RouteTable) -> None:
        """Registers the /api/cubes routes."""
        table.add("GET", "/api/cubes",              self.listing)
        table.add("GET", "/api/cubes/param_runs",   self.param_runs)
        table.add("GET", "/api/cubes/params_at",    self.params_at)
        table.add("GET", "/api/cubes/status",       self.status)
        table.add("GET", "/api/cubes/primary",      self.primary)
        table.add("GET", "/api/cubes/profiles",     self.profiles)
        table.add("GET", "/api/cubes/plane",        self.plane)
        table.add("GET", "/api/cubes/cbar",         self.cbar)
        table.add("GET", "/api/cubes/points",       self.points)
        table.add("GET", "/api/cubes/volume",       self.volume)
        table.add("GET", "/api/cubes/globe_points", self.globe_points)
        table.add("GET", "/api/cubes/globe_pauli",  self.globe_pauli)
        table.add("GET", "/api/cubes/dem_grid",     self.dem_grid)
        table.add("GET", "/api/cubes/transect",     self.transect)
        table.add("GET", "/api/cubes/slice",        self.slice_view)
        table.add("GET", "/api/cubes/pauli_map",    self.pauli_map)
        table.add("GET", "/api/cubes/pauli_at",     self.pauli_at)
        table.add("GET", "/api/cubes/pauli_summary", self.pauli_summary)
        table.add("GET", "/api/cubes/figures",      self.figures)
        table.add("GET", "/api/cubes/pass_map",     self.pass_map)
        table.add("GET", "/api/cubes/figure",       self.figure)

        table.add("POST", "/api/cubes/load",            self.load)
        table.add("POST", "/api/cubes/save_transect",   self.save_transect)
        table.add("POST", "/api/cubes/save_slices",     self.save_slices)
        table.add("POST", "/api/cubes/save_globe_tour", self.save_globe_tour)

    def listing(self, exchange: HttpExchange) -> None:
        """Answers with the preprocessing runs under the requested base."""
        exchange.send_json(self.cubes.list_cubes(exchange.text("base")))

    def param_runs(self, exchange: HttpExchange) -> None:
        """Answers with the parameter-run tags stored under the requested run."""
        exchange.send_result(self.cubes.param_runs(exchange.text("id")), 404)

    def params_at(self, exchange: HttpExchange) -> None:
        """Answers with the Gaussian slots of the parametrized tomogram at one pixel."""
        result = self.cubes.params_at(
            cube_id = exchange.text("id"),
            az      = exchange.integer("az"),
            rg      = exchange.integer("rg"),
        )
        exchange.send_result(result, 404)

    def status(self, exchange: HttpExchange) -> None:
        """Answers with the progress of the running cube load."""
        exchange.send_json(self.cubes.load_status())

    def primary(self, exchange: HttpExchange) -> None:
        """Answers with the PNG primary-amplitude map of the requested cube."""
        exchange.send_png(self.cubes.primary_png(exchange.text("id")))

    def profiles(self, exchange: HttpExchange) -> None:
        """Answers with the elevation profiles at one azimuth/range pixel."""
        result = self.cubes.profiles(
            cube_id = exchange.text("id"),
            az      = exchange.integer("az"),
            rg      = exchange.integer("rg"),
        )
        exchange.send_result(result, 404)

    def plane(self, exchange: HttpExchange) -> None:
        """Answers with the PNG horizontal plane cut at the requested height fraction."""
        png = self.cubes.plane_png(
            cube_id = exchange.text("id"),
            source  = exchange.text("source", "full"),
            frac    = exchange.number("frac"),
            space   = exchange.text("space", "physical"),
            cmap    = exchange.text("cmap", "jet"),
        )
        exchange.send_png(png)

    def cbar(self, exchange: HttpExchange) -> None:
        """Answers with the PNG colour bar of the requested colormap."""
        exchange.send_png(self.cubes.cbar_png(exchange.text("cmap", "viridis")))

    def points(self, exchange: HttpExchange) -> None:
        """Answers with the binary point cloud of the cube above the amplitude floor."""
        blob = self.cubes.points_bin(
            cube_id    = exchange.text("id"),
            source     = exchange.text("source", "full"),
            amp_min    = exchange.number("amp_min", "0.001"),
            max_points = exchange.integer("max", "60000"),
        )
        exchange.send_bytes(blob)

    def globe_points(self, exchange: HttpExchange) -> None:
        """Answers with the geocoded binary point cloud consumed by the globe view, optionally coloured by a Pauli map."""
        blob = self.cubes.globe_points_bin(
            cube_id    = exchange.text("id"),
            source     = exchange.text("source", "full"),
            amp_min    = exchange.number("amp_min", "0.001"),
            max_points = exchange.integer("max", "60000"),
            pauli_mode = exchange.text("pauli", ""),
            win_az     = exchange.integer("win_az", "1"),
            win_rg     = exchange.integer("win_rg", "1"),
            shared     = self._shared_stretch(exchange),
            cmap       = exchange.text("cmap", "viridis"),
        )
        exchange.send_bytes(blob)

    def globe_pauli(self, exchange: HttpExchange) -> None:
        """Answers with the north-up PNG of one Pauli map for the globe drape, its lon/lat rectangle in the X-Rectangle header and the rendered window in X-Window."""
        rendered = self.cubes.globe_pauli_png(
            cube_id = exchange.text("id"),
            mode    = exchange.text("mode", "rgb"),
            win_az  = exchange.integer("win_az", "1"),
            win_rg  = exchange.integer("win_rg", "1"),
            shared  = self._shared_stretch(exchange),
            cmap    = exchange.text("cmap", "viridis"),
        )
        if rendered is None:
            exchange.not_found()
            return

        png, rect, window = rendered
        exchange.send_png(png, headers={"X-Rectangle": ",".join(f"{value:.8f}" for value in rect), "X-Window": f"{window[0]},{window[1]}"})

    def volume(self, exchange: HttpExchange) -> None:
        """Answers with the quantised binary volume of one cube source."""
        blob = self.cubes.volume_bin(
            cube_id = exchange.text("id"),
            source  = exchange.text("source", "full"),
            max_dim = exchange.integer("max", "192"),
        )
        exchange.send_bytes(blob)

    def dem_grid(self, exchange: HttpExchange) -> None:
        """Answers with the binary DEM grid of the requested cube."""
        exchange.send_bytes(self.cubes.dem_grid_bin(cube_id=exchange.text("id")))

    @staticmethod
    def _parse_points(text: str) -> list:
        """Parses a `pts` query value of the form ``az,rg;az,rg;...`` into vertex pairs."""
        points = []
        for token in text.split(";"):
            parts = token.split(",")
            if len(parts) != 2:
                continue
            try:
                points.append((int(parts[0]), int(parts[1])))
            except ValueError:
                continue
        return points

    def transect(self, exchange: HttpExchange) -> None:
        """Answers with the PNG vertical transect along the polyline in `pts`."""
        png = self.cubes.transect_png(
            cube_id = exchange.text("id"),
            source  = exchange.text("source", "full"),
            points  = self._parse_points(exchange.text("pts")),
            space   = exchange.text("space", "physical"),
            cmap    = exchange.text("cmap", "jet"),
            dem     = exchange.integer("dem", "0") != 0,
        )
        exchange.send_png(png)

    def slice_view(self, exchange: HttpExchange) -> None:
        """Answers with the PNG azimuth- or range-fixed vertical slice of the cube."""
        png = self.cubes.slice_png(
            cube_id = exchange.text("id"),
            source  = exchange.text("source", "full"),
            axis    = exchange.text("axis", "range"),
            az      = exchange.integer("az"),
            rg      = exchange.integer("rg"),
            space   = exchange.text("space", "physical"),
            cmap    = exchange.text("cmap", "jet"),
            dem     = exchange.integer("dem", "0") != 0,
        )
        exchange.send_png(png)

    def pass_map(self, exchange: HttpExchange) -> None:
        """Answers with the PNG amplitude or interferometric-phase map of one pass."""
        png = self.cubes.pass_map_png(
            cube_id = exchange.text("id"),
            kind    = exchange.text("kind", "amplitude"),
            index   = exchange.integer("idx"),
            cmap    = exchange.text("cmap", "gray"),
        )
        exchange.send_png(png)

    def pauli_map(self, exchange: HttpExchange) -> None:
        """Answers with the PNG Pauli composite, one component power map or the dominant-mechanism map."""
        png = self.cubes.pauli_png(
            cube_id = exchange.text("id"),
            mode    = exchange.text("mode", "rgb"),
            win_az  = exchange.integer("win_az", "1"),
            win_rg  = exchange.integer("win_rg", "1"),
            shared  = self._shared_stretch(exchange),
            cmap    = exchange.text("cmap", "viridis"),
        )
        exchange.send_png(png)

    def pauli_at(self, exchange: HttpExchange) -> None:
        """Answers with the Pauli powers and mechanism shares at one pixel."""
        result = self.cubes.pauli_value_at(
            cube_id = exchange.text("id"),
            az      = exchange.integer("az"),
            rg      = exchange.integer("rg"),
            win_az  = exchange.integer("win_az", "1"),
            win_rg  = exchange.integer("win_rg", "1"),
        )
        exchange.send_result(result, 404)

    def pauli_summary(self, exchange: HttpExchange) -> None:
        """Answers with the scene-wide mechanism balance and colour stretch of the Pauli decomposition."""
        result = self.cubes.pauli_summary(
            cube_id = exchange.text("id"),
            win_az  = exchange.integer("win_az", "1"),
            win_rg  = exchange.integer("win_rg", "1"),
            shared  = self._shared_stretch(exchange),
        )
        exchange.send_result(result, 404)

    def figures(self, exchange: HttpExchange) -> None:
        """Answers with the figure files saved under the loaded run."""
        exchange.send_result(self.cubes.list_figures(exchange.text("id")))

    def figure(self, exchange: HttpExchange) -> None:
        """Serves one saved figure of the loaded run, or 404 outside its figure trees."""
        target = self.cubes.figure_file(exchange.text("id"), exchange.text("rel"))
        if target is None:
            exchange.not_found()
            return

        exchange.send_file(target, "max-age=300")

    def load(self, exchange: HttpExchange) -> None:
        """Starts loading the cube named in the request body, with an optional parameter run."""
        exchange.send_result(self.cubes.start_load(exchange.body.get("id", ""), exchange.body.get("param_tag")))

    def save_transect(self, exchange: HttpExchange) -> None:
        """Saves the transect polyline described in the request body as figures on disk."""
        body   = exchange.body
        result = self.cubes.save_transect(
            cube_id = body.get("id", ""),
            points  = [(int(pair[0]), int(pair[1])) for pair in body.get("pts") or [] if len(pair) == 2],
            space   = body.get("space", "physical"),
            cmap    = body.get("cmap", "jet"),
            dem     = bool(body.get("dem", False)),
        )
        exchange.send_result(result)

    def save_slices(self, exchange: HttpExchange) -> None:
        """Saves the slices through the pixel described in the request body as figures."""
        body   = exchange.body
        result = self.cubes.save_slices(
            cube_id = body.get("id", ""),
            az      = int(body.get("az", 0)),
            rg      = int(body.get("rg", 0)),
            space   = body.get("space", "physical"),
            cmap    = body.get("cmap", "jet"),
            dem     = bool(body.get("dem", False)),
        )
        exchange.send_result(result)

    def save_globe_tour(self, exchange: HttpExchange) -> None:
        """Saves the rendered globe camera tour carried as the raw request body."""
        result = self.cubes.save_globe_tour(
            cube_id = exchange.text("id"),
            move    = exchange.text("move"),
            clip    = exchange.blob,
        )
        exchange.send_result(result)


class SliceRouter(SubRouter):
    """Routes the /api/slices endpoints onto the multi-run slice collector and its mailer.

    Attributes:
        slices : Slice collector service answering the requests.
        mailer : Service mailing a rendered basket.
    """

    def __init__(self, slices: SliceCollector, mailer: SliceCollectionMailer) -> None:
        """Stores the slice collector and mailer services and declares their routes."""
        self.slices = slices
        self.mailer = mailer

        super().__init__(("/api/slices",))

    def declare(self, table: RouteTable) -> None:
        """Registers the /api/slices routes."""
        table.add("GET",  "/api/slices/info",          self.info)
        table.add("GET",  "/api/slices/primary",       self.primary)
        table.add("GET",  "/api/slices/slice",         self.slice_view)
        table.add("GET",  "/api/slices/mail_settings", self.mail_settings)
        table.add("POST", "/api/slices/collect",       self.collect)
        table.add("POST", "/api/slices/mail",          self.mail)

    def info(self, exchange: HttpExchange) -> None:
        """Answers with the axis extents and sources available for one cube."""
        exchange.send_result(self.slices.info(exchange.text("id")), 404)

    def primary(self, exchange: HttpExchange) -> None:
        """Answers with the PNG primary-amplitude map of one cube, cropped to its region."""
        exchange.send_png(self.slices.primary_png(exchange.text("id")))

    def slice_view(self, exchange: HttpExchange) -> None:
        """Answers with the PNG slice of one cube under an optional shared colour scale."""
        png = self.slices.slice_png(
            cube_id = exchange.text("id"),
            source  = exchange.text("source", "full"),
            axis    = exchange.text("axis", "range"),
            az      = exchange.integer("az"),
            rg      = exchange.integer("rg"),
            space   = exchange.text("space", "physical"),
            cmap    = exchange.text("cmap", "jet"),
            vmin    = exchange.optional_number("vmin"),
            vmax    = exchange.optional_number("vmax"),
        )
        exchange.send_png(png)

    def mail_settings(self, exchange: HttpExchange) -> None:
        """Answers with the default recipient and whether the SMTP password is available."""
        exchange.send_json(self.mailer.settings())

    def collect(self, exchange: HttpExchange) -> None:
        """Renders the posted basket of slices into one saved figure set."""
        body   = exchange.body
        result = self.slices.collect(
            items  = body.get("items") or [],
            shared = bool(body.get("shared", True)),
            name   = body.get("name", ""),
        )
        exchange.send_result(result)

    def mail(self, exchange: HttpExchange) -> None:
        """Renders the posted basket of slices, then mails it as zip attachments."""
        body   = exchange.body
        result = self.mailer.mail(
            items     = body.get("items") or [],
            shared    = bool(body.get("shared", True)),
            name      = body.get("name", ""),
            recipient = body.get("recipient", ""),
            note      = body.get("note", ""),
        )
        exchange.send_result(result)
