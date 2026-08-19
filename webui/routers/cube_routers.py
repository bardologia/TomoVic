"""API routes of the Cube Explorer and slice-collector tabs.

Exposes preprocessing-run listing and loading, parameter-run listing and the
per-pixel Gaussian readout of the parametrized tomogram, plane/slice/transect
renderings, colour bars, point clouds for the 3D and globe views, the DEM grid
and multi-run slice collection.
"""

from __future__ import annotations

from cube_explorer    import CubeExplorer, SliceCollector
from routers.dispatch import HttpExchange, RouteTable, SubRouter


class CubeRouter(SubRouter):
    """Routes the /api/cubes endpoints onto the cube explorer service.

    Attributes:
        cubes: Cube explorer service answering the requests.
    """

    def __init__(self, cubes: CubeExplorer) -> None:
        """Stores the cube explorer service and declares its routes."""
        self.cubes = cubes

        super().__init__(("/api/cubes",))

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
        table.add("GET", "/api/cubes/globe_points", self.globe_points)
        table.add("GET", "/api/cubes/dem_grid",     self.dem_grid)
        table.add("GET", "/api/cubes/transect",     self.transect)
        table.add("GET", "/api/cubes/slice",        self.slice_view)

        table.add("POST", "/api/cubes/load",          self.load)
        table.add("POST", "/api/cubes/save_transect", self.save_transect)
        table.add("POST", "/api/cubes/save_slices",   self.save_slices)

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
        """Answers with the geocoded binary point cloud consumed by the globe view."""
        blob = self.cubes.globe_points_bin(
            cube_id    = exchange.text("id"),
            source     = exchange.text("source", "full"),
            amp_min    = exchange.number("amp_min", "0.001"),
            max_points = exchange.integer("max", "60000"),
        )
        exchange.send_bytes(blob)

    def dem_grid(self, exchange: HttpExchange) -> None:
        """Answers with the binary DEM grid of the requested cube."""
        exchange.send_bytes(self.cubes.dem_grid_bin(cube_id=exchange.text("id")))

    def transect(self, exchange: HttpExchange) -> None:
        """Answers with the PNG vertical transect between two azimuth/range pixels."""
        png = self.cubes.transect_png(
            cube_id = exchange.text("id"),
            source  = exchange.text("source", "full"),
            az0     = exchange.integer("az0"),
            rg0     = exchange.integer("rg0"),
            az1     = exchange.integer("az1"),
            rg1     = exchange.integer("rg1"),
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

    def load(self, exchange: HttpExchange) -> None:
        """Starts loading the cube named in the request body, with an optional parameter run."""
        exchange.send_result(self.cubes.start_load(exchange.body.get("id", ""), exchange.body.get("param_tag")))

    def save_transect(self, exchange: HttpExchange) -> None:
        """Saves the transect described in the request body as a figure on disk."""
        body   = exchange.body
        result = self.cubes.save_transect(
            cube_id = body.get("id", ""),
            az0     = int(body.get("az0", 0)),
            rg0     = int(body.get("rg0", 0)),
            az1     = int(body.get("az1", 0)),
            rg1     = int(body.get("rg1", 0)),
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


class SliceRouter(SubRouter):
    """Routes the /api/slices endpoints onto the multi-run slice collector.

    Attributes:
        slices: Slice collector service answering the requests.
    """

    def __init__(self, slices: SliceCollector) -> None:
        """Stores the slice collector service and declares its routes."""
        self.slices = slices

        super().__init__(("/api/slices",))

    def declare(self, table: RouteTable) -> None:
        """Registers the /api/slices routes."""
        table.add("GET",  "/api/slices/info",    self.info)
        table.add("GET",  "/api/slices/slice",   self.slice_view)
        table.add("POST", "/api/slices/collect", self.collect)

    def info(self, exchange: HttpExchange) -> None:
        """Answers with the axis extents and sources available for one cube."""
        exchange.send_result(self.slices.info(exchange.text("id")), 404)

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

    def collect(self, exchange: HttpExchange) -> None:
        """Collects the requested slices of several cubes into one saved figure set."""
        body   = exchange.body
        result = self.slices.collect(
            ids     = body.get("ids") or [],
            points  = body.get("points") or [],
            sources = body.get("sources") or [],
            axes    = body.get("axes") or [],
            space   = body.get("space", "physical"),
            cmap    = body.get("cmap", "jet"),
            shared  = bool(body.get("shared", True)),
            name    = body.get("name", ""),
        )
        exchange.send_result(result)
