"""Tests of adding missing pieces to a TomoVis import, and of the cache invalidation that follows.

Every add flow writes into the import's own folder only (picked .npy files are
linked, parameter runs copied), raises the revisions as the bridge promises,
and leaves a run the Cube explorer loads with the new piece. Every refusal
carries the exact sentence the pages show. A piece added to a run directory
changes what its next load reads, so both the cube explorer and the slice
collector drop everything they hold for that run.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import h5py
import numpy as np
import pytest

from tests.webui.bridge_fixtures  import INPUTS, BridgeHarness, StalledPreparer
from tests.webui.conftest         import N_AZ, N_ELEV, N_RG, load_cube
from tests.webui.preproc_fixtures import make_param_run, make_preproc_run, open_runs

from bridge.array_check    import PieceError
from bridge.dataset_bridge import BridgeRefusal
from cube_explorer         import SliceCollector
from web_logger            import WebLogger


class ForgetCase:
    """Two loaded runs and a slice collector that opened both."""

    def __init__(self, base) -> None:
        """Builds two runs with a geocoded scene, loads both and opens both in the collector.

        Args:
            base : Folder the runs are written under.
        """

        make_preproc_run(base, name="run_a", with_geo=True)
        make_preproc_run(base, name="run_b", with_geo=True)
        self.explorer, self.ids = open_runs(base, expected=2)
        self.slices             = SliceCollector(self.explorer, WebLogger("forget-test"))

        for run_id in self.ids:
            load_cube(self.explorer, run_id)
            self.explorer.load_thread.join()
            assert self.slices.info(run_id)["ok"]

    def cached(self, run_id: str) -> tuple[int, int]:
        """Returns how many cube states and globe blobs the explorer holds for a run."""

        prefix = f"{run_id}|"
        return sum(key.startswith(prefix) for key in self.explorer.cube_cache.entries), sum(key.startswith(prefix) for key in self.explorer.globe_blobs.entries)


def test_forgetting_the_loaded_run_unloads_it_and_drops_its_caches(tmp_path):
    """forget() of the loaded run empties its cache entries and returns the status to idle; the other run keeps its entries."""

    case          = ForgetCase(tmp_path)
    first, second = case.ids

    assert case.cached(second)[0] == 1 and case.cached(second)[1] >= 1
    case.explorer.forget(second)

    assert case.cached(second) == (0, 0)
    assert case.cached(first)[0] == 1
    assert case.explorer.loaded is None
    assert case.explorer.load_status()["state"] == "idle"


def test_forgetting_another_run_keeps_the_loaded_cube(tmp_path):
    """forget() of a run that is not loaded leaves the loaded cube and its status alone."""

    case          = ForgetCase(tmp_path)
    first, second = case.ids

    case.explorer.forget(first)

    assert case.cached(first) == (0, 0)
    assert case.explorer.load_status()["state"] == "ready"
    assert case.explorer.loaded["id"] == second


def test_the_slice_collector_forgets_one_context(tmp_path):
    """SliceCollector.forget() drops the context of that run only."""

    case          = ForgetCase(tmp_path)
    first, second = case.ids

    case.slices.forget(first)

    assert case.slices.contexts.get(first) is None
    assert case.slices.contexts.get(second) is not None


class PieceCase:
    """A 3-D import over the synthetic run footprint, with helpers to write picked files and add pieces.

    Attributes:
        tmp     : Test folder.
        files   : Folder of the files the user picks.
        harness : Bridge harness.
        record  : The import's record.
        id      : The import's dataset id.
    """

    def __init__(self, tmp_path: Path, cube: np.ndarray | None = None, name: str = "cube.npy") -> None:
        """Imports a (N_ELEV, N_AZ, N_RG) cube and waits for its preparation.

        Args:
            tmp_path : Test folder.
            cube     : Cube to import; a random float32 cube when None.
            name     : File name of the imported cube.
        """

        self.tmp     = tmp_path
        self.files   = tmp_path / "files"
        self.files.mkdir(parents=True)
        self.harness = BridgeHarness(tmp_path)
        cube         = np.random.default_rng(7).random((N_ELEV, N_AZ, N_RG)).astype(np.float32) if cube is None else cube
        self.record  = self.harness.imported("npy", self.save(name, cube))
        self.id      = self.record.id

    def save(self, name: str, array: np.ndarray) -> str:
        """Writes a file the user picks and returns its path."""

        path = self.files / name
        np.save(path, array)
        return str(path)

    def add(self, piece: str, **fields) -> dict:
        """Adds a piece and returns the Dataset payload, after any preparation it started."""

        self.harness.bridge.add(self.id, piece, fields)
        self.harness.settle()
        return self.harness.dataset(self.id)

    def refused(self, piece: str, **fields) -> str:
        """Adds a piece that must be refused and returns the refusal sentence."""

        with pytest.raises(PieceError) as error:
            self.harness.bridge.add(self.id, piece, fields)
        assert error.value.piece == piece
        return str(error.value)

    def run(self, name: str = "run_a", **kwargs) -> Path:
        """Writes a synthetic TomoVic run with the same footprint."""

        return make_preproc_run(self.tmp / "runs", name=name, **kwargs)

    def load(self) -> dict:
        """Loads the import in the Cube explorer and returns the cube metadata."""

        return load_cube(self.harness.cubes, self.id)["cube"]

    def layout(self) -> dict:
        """Returns the import's dataset.json."""

        return json.loads((Path(self.id) / "data" / "dataset.json").read_text())

    def complex_stack(self, shape: tuple) -> np.ndarray:
        """Returns a random complex64 array."""

        rng = np.random.default_rng(11)
        return (rng.normal(size=shape) + 1j * rng.normal(size=shape)).astype(np.complex64)


def test_adding_a_height_range(tmp_path):
    """Heights go to config_state.json and the link; both revisions rise; the current dataset becomes set by TomoVic; the Cube loads in metres."""

    case    = PieceCase(tmp_path)
    before  = (case.record.revision, case.record.tomovis_revision, case.harness.bridge.current["serial"])
    dataset = case.add("height_range", low=-20, high=80)

    assert dataset["pieces"]["height_range"]["value"] == [-20.0, 80.0] and dataset["pieces"]["height_range"]["origin"] == "added"
    assert (case.record.revision, case.record.tomovis_revision) == (before[0] + 1, before[1] + 1)
    assert case.harness.bridge.current == {"id": case.id, "serial": before[2] + 1, "set_by": "tomovic"}
    assert dataset["tomovis"]["revision"] == before[1] + 1 and dataset["tools"]["cube"]["ready"]
    with h5py.File(dataset["tomovis"]["link"], "r") as h5f:
        assert h5f["tomogram"].attrs["range"] == "[-20.0, 80.0]"

    meta = case.load()
    assert (meta["x_min"], meta["x_max"]) == (-20.0, 80.0)


def test_adding_a_pixel_spacing(tmp_path):
    """The spacing is a one-track track_parameters.json; TomoVis's link carries it and the Cube shows a metric scale."""

    case    = PieceCase(tmp_path)
    case.add("height_range", low=0, high=10)
    dataset = case.add("spacing", azimuth=0.4, range=0.6)
    tracks  = json.loads((Path(case.id) / "meta" / "track_parameters.json").read_text())

    assert tracks == {"labels": ["bridge"], "reference": "bridge", "shared": {"ps_az": 0.4, "ps_rg": 0.6}, "per_track": {"bridge": {}}, "track_files": []}
    assert dataset["pieces"]["spacing"]["value"] == [0.4, 0.6] and case.record.tomovis_revision == 2
    assert dataset["tools"]["tomovis_metres"]["ready"] and dataset["tools"]["cube_metric"]["ready"]
    with h5py.File(dataset["tomovis"]["link"], "r") as h5f:
        assert h5f.attrs["ps_az"] == "0.4" and h5f.attrs["ps_rg"] == "0.6"
    assert case.load()["spacing"] == {"az": 0.4, "rg": 0.6}


def test_choosing_a_channel(tmp_path):
    """A channel choice rebuilds the tomogram and the stand-in primary; an index out of range is refused with the exact sentence."""

    case    = PieceCase(tmp_path, np.load(INPUTS / "npy_channels_3.npy"), "three.npy")
    cube    = np.load(INPUTS / "npy_channels_3.npy")
    before  = case.record.revision
    dataset = case.add("channel", choice=2)

    assert dataset["channel"]["chosen"] == 2 and dataset["state"] == "ready"
    assert np.allclose(np.load(Path(case.id) / "data" / "tomogram_full.npy"), np.abs(cube[2]))
    assert case.record.revision == before + 2
    assert case.refused("channel", choice=3) == 'Choose "combined" or a channel number from 0 to 2.'
    assert case.refused("channel", choice="all") == 'Choose "combined" or a channel number from 0 to 2.'
    assert case.add("channel", choice="combined")["pieces"]["tomogram"]["origin"] == "combined channel"


def test_replacing_and_rebuilding_the_primary(tmp_path):
    """A picked primary is linked to its resolved file; 'cube' rebuilds the stand-in in place of the link."""

    case    = PieceCase(tmp_path)
    picked  = case.save("slc.npy", case.complex_stack((N_AZ, N_RG)))
    dataset = case.add("primary", **{"from": "file", "path": picked})
    target  = Path(case.id) / "data" / "primary.npy"

    assert target.is_symlink() and target.resolve() == Path(picked).resolve()
    assert dataset["pieces"]["primary"]["value"] == {"kind": "file"} and case.record.linked["primary"] == str(Path(picked).resolve())

    rebuilt = case.add("primary", **{"from": "cube"})
    assert not target.is_symlink() and rebuilt["pieces"]["primary"]["value"] == {"kind": "stand-in"}
    assert np.array_equal(np.load(picked), case.complex_stack((N_AZ, N_RG)))


def test_adding_a_dem_reloads_with_terrain(tmp_path):
    """Load, add a DEM, load again: the cache was dropped and the Cube now has a DEM."""

    case = PieceCase(tmp_path)
    case.add("height_range", low=0, high=10)
    assert case.load()["dem"] is False

    dem       = np.full((N_AZ, N_RG), 500.0, dtype=np.float32)
    dem[0, 0] = np.nan
    dataset   = case.add("dem", path=case.save("dem.npy", dem))

    assert dataset["pieces"]["dem"]["present"] and case.layout()["artifacts"]["dem_full"] == "dem_full.npy"
    assert case.harness.cubes.loaded is None
    assert case.load()["dem"] is True


def test_copying_geometry_from_a_run_opens_the_globe(tmp_path):
    """The run's track parameters are copied, its DEM linked, its crop and pass labels written; the import then loads with a globe."""

    case    = PieceCase(tmp_path)
    run_dir = case.run(with_geo=True, with_dem=True)
    case.add("height_range", low=0, high=10)
    dataset = case.add("geometry", run=str(run_dir))
    meta    = Path(case.id) / "meta"

    assert not (meta / "track_parameters.json").is_symlink()
    assert (meta / "track_parameters.json").read_bytes() == (run_dir / "meta" / "track_parameters.json").read_bytes()
    assert (Path(case.id) / "data" / "dem_full.npy").resolve() == (run_dir / "data" / "dem_full.npy").resolve()
    assert case.layout()["pass_labels"] == ["T01", "T02"] and case.layout()["global_crop"] == [0, N_AZ, 0, N_RG]
    assert dataset["pieces"]["geometry"]["value"] == {"run": str(run_dir.resolve()), "geometry_field": False}
    assert dataset["pieces"]["spacing"]["origin"] == "copied from run_a" and dataset["pieces"]["dem"]["origin"] == "copied from run_a"
    assert dataset["tools"]["cube_globe"]["ready"] and case.record.tomovis_revision == 2
    assert case.load()["globe"] is not None


def test_adding_a_pass_stack_after_the_geometry(tmp_path):
    """One secondary for a two-pass geometry, with interferograms: the Passes view loads."""

    case    = PieceCase(tmp_path)
    case.add("height_range", low=0, high=10)
    case.add("geometry", run=str(case.run(with_geo=True, with_dem=True)))
    stack   = case.complex_stack((1, N_AZ, N_RG))
    dataset = case.add("passes", secondaries=case.save("sec.npy", stack), interferograms=case.save("ifg.npy", stack))

    assert dataset["pieces"]["passes"]["value"] == {"secondaries": 1, "interferograms": True}
    assert case.load()["passes"] == {"labels": ["T01", "T02"], "n_passes": 2, "phase": True}

    again = case.add("passes", secondaries=case.save("sec_b.npy", stack), interferograms=None)
    assert again["pieces"]["passes"]["value"] == {"secondaries": 1, "interferograms": False}
    assert "interferograms" not in case.layout()["artifacts"]


def test_adding_a_polarimetric_primary_opens_pauli(tmp_path):
    """A complex 3 x az x rg stack and its window: the sidecar is written and the Pauli view loads."""

    case    = PieceCase(tmp_path)
    case.add("height_range", low=0, high=10)
    dataset = case.add("polarimetry", path=case.save("pol.npy", case.complex_stack((3, N_AZ, N_RG))), window=[2, 3])
    sidecar = json.loads((Path(case.id) / "meta" / "primary_polarimetric.json").read_text())

    assert sidecar == {"channels": ["hh", "xx", "vv"], "window": [2, 3]}
    assert dataset["pieces"]["polarimetry"]["value"] == {"window": [2, 3]} and dataset["tools"]["cube_pauli"]["ready"]
    assert case.load()["pauli"]["window"] == [2, 3]


def test_a_parameter_run_is_copied_not_linked(tmp_path):
    """The folder's files are copied into params/<name>; the same name again lands in <name>_2; the Cube lists both tags."""

    case   = PieceCase(tmp_path)
    folder = make_param_run(tmp_path / "fit", "params_k2")
    case.add("height_range", low=-10, high=30)
    case.add("params", path=str(folder))
    dataset = case.add("params", path=str(folder))
    copied  = Path(case.id) / "params" / "params_k2"

    assert sorted(path.name for path in copied.iterdir()) == ["fit_diagnostics.npz", "param_extraction_meta.json", "parameters.npy"]
    assert not any(path.is_symlink() for path in copied.iterdir())
    assert dataset["pieces"]["params"]["value"] == {"tags": ["params_k2", "params_k2_2"]}
    assert dataset["pieces"]["params"]["launch"] == {"script": "extract_params", "label": "Fit with Extract Params", "overrides": {"dataset_base_path": str(Path(case.id).parent), "dataset_filter": [Path(case.id).name]}}
    assert case.harness.cubes.param_runs(case.id)["tags"] == ["params_k2", "params_k2_2"]


class Messages:
    """Builds each refused add and the exact sentence it must give (the design's section 4.4)."""

    @staticmethod
    def cases() -> dict:
        """Returns case name to a callable(case) -> (piece, fields, expected sentence)."""

        complex_plane = lambda case: case.complex_stack((N_AZ, N_RG))
        return {
            "not_npy"         : lambda case: ("dem", {"path": str(case.files / "dem.txt")}, "Pick a .npy file; dem.txt is not one."),
            "unreadable"      : lambda case: ("dem", {"path": str(case.files / "missing.npy")}, "Could not read missing.npy: No such file or directory."),
            "fortran"         : lambda case: ("primary", {"from": "file", "path": case.save("fortran.npy", np.asfortranarray(np.ones((N_AZ, N_RG), dtype=np.float32)))}, "fortran.npy is stored in Fortran order. Save it in C order (numpy.ascontiguousarray) and pick it again."),
            "not_numbers"     : lambda case: ("primary", {"from": "file", "path": case.save("flags.npy", np.zeros((N_AZ, N_RG), dtype=bool))}, "flags.npy holds bool values; Primary image needs real or complex numbers."),
            "plane_shape"     : lambda case: ("primary", {"from": "file", "path": case.save("wrong.npy", np.ones((10, 10)))}, f"Primary image must be azimuth x range = {N_AZ} x {N_RG} like the tomogram, but wrong.npy has shape 10 x 10."),
            "dem_complex"     : lambda case: ("dem", {"path": case.save("dem_c.npy", complex_plane(case))}, "A DEM holds heights in metres, so it must be real; dem_c.npy is complex64."),
            "dem_shape"       : lambda case: ("dem", {"path": case.save("dem_s.npy", np.ones((3, 3)))}, f"DEM must be azimuth x range = {N_AZ} x {N_RG} like the tomogram, but dem_s.npy has shape 3 x 3."),
            "dem_no_finite"   : lambda case: ("dem", {"path": case.save("dem_nan.npy", np.full((N_AZ, N_RG), np.nan))}, "dem_nan.npy holds no finite height."),
            "stack_shape"     : lambda case: ("passes", {"secondaries": case.save("sec_bad.npy", np.ones((2, N_AZ - 1, N_RG)))}, f"The pass stack must be passes x azimuth x range with azimuth x range = {N_AZ} x {N_RG}; sec_bad.npy has shape 2 x {N_AZ - 1} x {N_RG}."),
            "ifg_shape"       : lambda case: ("passes", {"secondaries": case.save("sec.npy", np.ones((2, N_AZ, N_RG))), "interferograms": case.save("ifg.npy", np.ones((1, N_AZ, N_RG)))}, f"The interferograms must have the shape of the secondaries 2 x {N_AZ} x {N_RG}; ifg.npy has shape 1 x {N_AZ} x {N_RG}."),
            "pol_shape"       : lambda case: ("polarimetry", {"path": case.save("pol_s.npy", case.complex_stack((2, N_AZ, N_RG))), "window": [1, 1]}, f"The polarimetric primary must be 3 x azimuth x range = 3 x {N_AZ} x {N_RG} (channels HH, cross, VV); pol_s.npy has shape 2 x {N_AZ} x {N_RG}."),
            "pol_real"        : lambda case: ("polarimetry", {"path": case.save("pol_r.npy", np.ones((3, N_AZ, N_RG), dtype=np.float32)), "window": [1, 1]}, "The polarimetric primary must be complex; pol_r.npy is float32."),
            "window"          : lambda case: ("polarimetry", {"path": case.save("pol.npy", case.complex_stack((3, N_AZ, N_RG))), "window": [0, 2]}, "The multilook window must be two whole numbers from 1 to 99."),
            "window_float"    : lambda case: ("polarimetry", {"path": case.save("pol.npy", case.complex_stack((3, N_AZ, N_RG))), "window": [1.5, 2]}, "The multilook window must be two whole numbers from 1 to 99."),
            "no_parameters"   : lambda case: ("params", {"path": str(case.files)}, "files holds no parameters.npy."),
            "no_meta"         : lambda case: Messages.params_without_meta(case),
            "params_shape"    : lambda case: Messages.params_with(case, np.ones((4, N_AZ, N_RG), dtype=np.float32), 1, f"parameters.npy must be 3k x azimuth x range with azimuth x range = {N_AZ} x {N_RG}; it has shape 4 x {N_AZ} x {N_RG}."),
            "params_k_max"    : lambda case: Messages.params_with(case, np.ones((6, N_AZ, N_RG), dtype=np.float32), 3, "param_extraction_meta.json says k_max = 3, but parameters.npy holds 2 Gaussians."),
            "heights_text"    : lambda case: ("height_range", {"low": "a", "high": 3}, "Both heights must be numbers."),
            "heights_order"   : lambda case: ("height_range", {"low": 5, "high": 5}, "The lower height must be below the upper height."),
            "spacing"         : lambda case: ("spacing", {"azimuth": -1, "range": 0.5}, "Both spacings must be positive numbers of metres."),
            "not_a_run"       : lambda case: ("geometry", {"run": str(case.files)}, f"{case.files} is not a TomoVic run: it holds no data/dataset.json."),
            "no_tracks"       : lambda case: ("geometry", {"run": str(case.run())}, "run_a has no meta/track_parameters.json."),
            "tracks_lack"     : lambda case: ("geometry", {"run": str(case.run(with_spacing=True))}, "The track parameters of run_a lack h0, heading, squint, antdir, r, geo_poly, so they cannot place the scene on the globe."),
            "other_footprint" : lambda case: Messages.other_footprint(case),
            "labels_passes"   : lambda case: Messages.labels_against_passes(case),
        }

    @staticmethod
    def params_without_meta(case) -> tuple:
        """A parameter folder holding parameters.npy only."""

        folder = case.files / "fit"
        folder.mkdir()
        np.save(folder / "parameters.npy", np.ones((6, N_AZ, N_RG), dtype=np.float32))
        return "params", {"path": str(folder)}, "fit holds no param_extraction_meta.json."

    @staticmethod
    def params_with(case, parameters: np.ndarray, k_max: int, message: str) -> tuple:
        """A parameter folder with the given parameters and k_max."""

        folder = case.files / "fit"
        folder.mkdir()
        np.save(folder / "parameters.npy", parameters)
        (folder / "param_extraction_meta.json").write_text(json.dumps({"k_max": k_max}))
        return "params", {"path": str(folder)}, message

    @staticmethod
    def other_footprint(case) -> tuple:
        """A geocoded run whose crop spans another footprint."""

        run_dir = case.run(with_geo=True)
        layout  = json.loads((run_dir / "data" / "dataset.json").read_text())
        layout["global_crop"] = [0, 4, 0, N_RG]
        (run_dir / "data" / "dataset.json").write_text(json.dumps(layout))
        return "geometry", {"run": str(run_dir)}, f"run_a covers 4 x {N_RG} pixels but cube.npy is {N_AZ} x {N_RG}; geometry can only be copied from a run with the same footprint."

    @staticmethod
    def labels_against_passes(case) -> tuple:
        """Two secondaries after a two-pass geometry was copied."""

        case.harness.bridge.add(case.id, "geometry", {"run": str(case.run(with_geo=True))})
        return "passes", {"secondaries": case.save("sec2.npy", np.ones((2, N_AZ, N_RG)))}, "The acquisition geometry copied from run_a names 2 passes, so the pass stack must hold 1 secondaries; sec2.npy holds 2."


@pytest.mark.parametrize("name", sorted(Messages.cases()))
def test_every_refusal_gives_its_exact_sentence(tmp_path, name):
    """Each refused add raises PieceError with the piece and the design's sentence, and changes nothing."""

    case                    = PieceCase(tmp_path)
    piece, fields, expected = Messages.cases()[name](case)
    revision                = case.record.revision

    assert case.refused(piece, **fields) == expected
    assert case.record.revision == revision


def test_geometry_with_more_passes_than_the_stack_is_refused(tmp_path):
    """Copying a two-pass geometry onto an import holding two secondaries is refused with the pass-count sentence."""

    case = PieceCase(tmp_path)
    case.add("passes", secondaries=case.save("sec2.npy", np.ones((2, N_AZ, N_RG))))

    assert case.refused("geometry", run=str(case.run(with_geo=True))) == "The acquisition geometry copied from run_a names 2 passes, so the pass stack must hold 1 secondaries; sec2.npy holds 2."


def test_runs_are_never_written(tmp_path):
    """Adding to a registered or an unregistered run is refused with 400; an unknown id is 404."""

    case    = PieceCase(tmp_path)
    run_dir = case.run()
    case.harness.open_runs_root(tmp_path / "runs")
    message = "run_a is a TomoVic run; the bridge never writes into run folders."

    with pytest.raises(BridgeRefusal) as unregistered:
        case.harness.bridge.add(str(run_dir), "dem", {"path": "/x.npy"})
    case.harness.bridge.use(str(run_dir))
    with pytest.raises(BridgeRefusal) as registered:
        case.harness.bridge.add(str(run_dir), "dem", {"path": "/x.npy"})
    with pytest.raises(BridgeRefusal) as unknown:
        case.harness.bridge.add(str(tmp_path / "nothing"), "dem", {"path": "/x.npy"})

    assert (unregistered.value.status, str(unregistered.value), unregistered.value.piece) == (400, message, "dem")
    assert (registered.value.status, str(registered.value)) == (400, message)
    assert (unknown.value.status, str(unknown.value)) == (404, f"unknown dataset: {tmp_path / 'nothing'}")


def test_adds_wait_for_preparation_and_for_a_cube_load(tmp_path):
    """409 while the import is preparing and while the Cube page is loading it."""

    harness = BridgeHarness(tmp_path, start=False)
    harness.bridge.preparer = StalledPreparer(harness.workspace, harness.logger, harness.bridge.prepared)
    harness.bridge.start()
    harness.bridge.tomovis_imported("window-a", "npy", str(INPUTS / "npy_real.npy"))
    dataset_id = harness.bridge.current["id"]

    with pytest.raises(BridgeRefusal) as preparing:
        harness.bridge.add(dataset_id, "height_range", {"low": 0, "high": 1})
    assert (preparing.value.status, str(preparing.value)) == (409, "npy_real.npy is still being prepared for the TomoVic tools.")

    case = PieceCase(tmp_path / "second")
    case.harness.cubes.status = {"state": "loading", "id": case.id, "progress": 0.0, "stage": "", "error": ""}
    with pytest.raises(BridgeRefusal) as loading:
        case.harness.bridge.add(case.id, "height_range", {"low": 0, "high": 1})
    assert (loading.value.status, str(loading.value)) == (409, "The Cube page is still loading cube.npy. Add the piece when it is ready.")


def test_spacing_replaces_a_copied_geometry(tmp_path):
    """Typing a spacing after a geometry copy writes one-track parameters, so the geometry piece is gone and the link has the new spacing."""

    case = PieceCase(tmp_path)
    case.add("geometry", run=str(case.run(with_geo=True)))
    dataset = case.add("spacing", azimuth=1.5, range=2.5)

    assert not dataset["pieces"]["geometry"]["present"] and "geometry" not in case.record.linked
    assert dataset["pieces"]["spacing"]["value"] == [1.5, 2.5] and dataset["pieces"]["spacing"]["origin"] == "added"
