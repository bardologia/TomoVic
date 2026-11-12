"""Tests of the preparation that turns a TomoVis import into a run the TomoVic tools read.

Every import format is converted with TomoVis's own readers when it is not a
C-ordered .npy, checked, reduced to a 3-D float32 tomogram when it has
channels, and given a stand-in primary image; the facts the source carries
(hd5 attributes, session metadata) become the height range and pixel spacing.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from tests.webui.bridge_fixtures import INPUTS, SESSIONS, BridgeHarness, FixtureCopies, StalledPreparer

from bridge.cube_preparer import CubePreparer, PreparationJob
from tomovis.cube_readers import CubeReaders
from tomovis.session_file import SessionFile
from web_logger           import WebLogger


class Prepared:
    """One import prepared in a fresh harness, with its files at hand.

    Attributes:
        harness : The harness.
        record  : The dataset record.
        folder  : The dataset folder.
        dataset : The Dataset payload.
    """

    def __init__(self, tmp_path: Path, kind: str, source: Path) -> None:
        """Imports the source and waits for its preparation.

        Args:
            tmp_path : Test folder.
            kind     : Import kind.
            source   : Imported file.
        """

        self.harness = BridgeHarness(tmp_path)
        self.record  = self.harness.imported(kind, source)
        self.folder  = Path(self.record.id)
        self.dataset = self.harness.dataset(self.record.id)

    def array(self, name: str) -> np.ndarray:
        """Loads data/<name>."""

        return np.load(self.folder / "data" / name)

    def piece(self, key: str) -> dict:
        """Returns one Piece of the payload."""

        return self.dataset["pieces"][key]


def standin(tomogram: np.ndarray) -> np.ndarray:
    """Whole-array stand-in primary: sqrt(sum over elevation of |tomogram|), non-finite samples as 0."""

    magnitude = np.abs(tomogram.astype(np.complex128) if np.iscomplexobj(tomogram) else tomogram.astype(np.float64))
    magnitude[~np.isfinite(magnitude)] = 0.0
    return np.sqrt(magnitude.sum(axis=0)).astype(np.float32)


def test_a_c_ordered_3d_npy_is_linked_with_a_standin_primary(tmp_path):
    """npy_real: the tomogram is a link to the user's file, the TomoVis link exists, the stand-in equals the formula and no height range is known."""

    case = Prepared(tmp_path, "npy", INPUTS / "npy_real.npy")
    cube = np.load(INPUTS / "npy_real.npy")

    assert (case.folder / "data" / "tomogram_full.npy").resolve() == (INPUTS / "npy_real.npy").resolve()
    assert not (case.folder / "data" / "tomovis_cube.npy").exists()
    assert case.dataset["tomovis"]["ready"]
    assert np.array_equal(CubeReaders(WebLogger()).fusar(case.dataset["tomovis"]["link"]).data, cube)
    assert np.allclose(case.array("primary.npy"), standin(cube))
    assert case.piece("primary")["value"] == {"kind": "stand-in"} and case.piece("primary")["origin"] == "stand-in"
    assert not case.piece("height_range")["present"]
    assert case.dataset["state"] == "ready" and case.record.revision == 1
    assert json.loads((case.folder / "data" / "dataset.json").read_text())["global_crop"] == [0, 32, 0, 24]


def test_the_link_exists_as_soon_as_an_npy_is_registered(tmp_path):
    """A C-ordered .npy gets its TomoVis link inside the import request, before any preparation ran."""

    harness = BridgeHarness(tmp_path, start=False)
    harness.bridge.preparer = StalledPreparer(harness.workspace, harness.logger, harness.bridge.prepared)
    harness.bridge.start()
    harness.bridge.tomovis_imported("window-a", "npy", str(INPUTS / "npy_real.npy"))
    dataset = harness.dataset(harness.bridge.current["id"])

    assert dataset["state"] == "preparing"
    assert dataset["tomovis"]["ready"]
    assert dataset["tools"]["tomovis"]["ready"]


def test_a_fusar_hd5_is_converted_with_its_attributes(tmp_path):
    """fusar_two_key_elev: converted to tomovis_cube.npy, heights [-10, 30] and spacing 0.5 x 0.75 from the hd5, tomovis_revision 0."""

    case = Prepared(tmp_path, "hd5", INPUTS / "fusar_two_key_elev.hd5")

    assert np.array_equal(case.array("tomovis_cube.npy"), CubeReaders(WebLogger()).fusar(str(INPUTS / "fusar_two_key_elev.hd5")).data)
    assert case.piece("height_range")["value"] == [-10.0, 30.0] and case.piece("height_range")["origin"] == "hd5 attributes"
    assert case.piece("spacing")["value"] == [0.5, 0.75] and case.piece("spacing")["origin"] == "hd5 attributes"
    assert case.record.tomovis_revision == 0
    assert case.dataset["tools"]["cube"]["ready"] and case.dataset["tools"]["tomovis_metres"]["ready"]


def test_a_fusar_hd5_without_attributes_has_no_height_range(tmp_path):
    """fusar_no_attrs: converted, but neither heights nor spacing are known."""

    case = Prepared(tmp_path, "hd5", INPUTS / "fusar_no_attrs.hd5")

    assert not case.piece("height_range")["present"] and not case.piece("spacing")["present"]
    assert case.dataset["tools"]["cube"]["missing"] == ["height_range"]


def test_a_uavsar_h5_equals_the_tomovis_reader(tmp_path):
    """uavsar_three_keys: the converted cube is CubeReaders.uavsar of the file."""

    case = Prepared(tmp_path, "h5", INPUTS / "uavsar_three_keys.h5")

    assert np.array_equal(case.array("tomovis_cube.npy"), CubeReaders(WebLogger()).uavsar(str(INPUTS / "uavsar_three_keys.h5")))
    assert case.dataset["origin_label"] == "TomoVis import · h5"


def test_a_rat_file_equals_the_tomovis_reader(tmp_path):
    """rat_complex: the converted cube is CubeReaders.rat of the file."""

    case = Prepared(tmp_path, "rat", INPUTS / "rat_complex.rat")

    assert np.array_equal(case.array("tomovis_cube.npy"), CubeReaders(WebLogger()).rat(str(INPUTS / "rat_complex.rat")), equal_nan=True)
    assert case.dataset["state"] == "ready"


def test_a_session_brings_its_metadata_facts(tmp_path):
    """A TomoVis session: its data is converted and z_min/z_max and x_res/y_res become heights and spacing."""

    path     = SESSIONS / "mono_profile.hd5"
    case     = Prepared(tmp_path, "session", path)
    metadata = SessionFile().metadata(str(path))

    assert np.array_equal(case.array("tomovis_cube.npy"), SessionFile().read(str(path))[0])
    assert case.piece("height_range")["value"] == [float(metadata["z_min"]), float(metadata["z_max"])]
    assert case.piece("spacing")["value"] == [float(metadata["x_res"]), float(metadata["y_res"])]
    assert case.piece("height_range")["origin"] == "TomoVis session"
    assert case.dataset["origin_label"] == "TomoVis session"


def test_a_session_without_metadata_has_no_facts(tmp_path):
    """no_metadata.hd5: converted, heights and spacing unknown."""

    case = Prepared(tmp_path, "session", SESSIONS / "no_metadata.hd5")

    assert case.dataset["state"] == "ready"
    assert not case.piece("height_range")["present"]


def test_a_session_holding_tomovis_defaults_has_no_facts(tmp_path):
    """green_plot.hd5 saved z 0..15 (the range-sample default) and 1 x 1 spacing: neither counts as a measured value."""

    case = Prepared(tmp_path, "session", SESSIONS / "green_plot.hd5")
    slab = Prepared(tmp_path / "slice", "session", SESSIONS / "slice_mode.hd5")

    assert case.dataset["state"] == "ready"
    assert not case.piece("height_range")["present"] and not case.piece("spacing")["present"]
    assert slab.piece("height_range")["value"] == [0.0, 45.0] and not slab.piece("spacing")["present"]


def test_three_channels_give_the_combined_channel_then_channel_two(tmp_path):
    """npy_channels_3: the tomogram is sqrt(sum_c |x_c|^2); choosing channel index 1 rewrites it as |x_1|."""

    case = Prepared(tmp_path, "npy", INPUTS / "npy_channels_3.npy")
    cube = np.load(INPUTS / "npy_channels_3.npy")

    assert case.dataset["channel"] == {"choices": ["combined", 0, 1, 2], "chosen": "combined"}
    assert case.dataset["cube"]["channels"] == 3
    assert np.allclose(case.array("tomogram_full.npy"), np.sqrt((np.abs(cube) ** 2).sum(axis=0)))
    assert case.piece("tomogram")["origin"] == "combined channel"
    assert case.dataset["tomovis"]["scripts_link"].endswith("tomovis_scripts.hd5")

    case.record.channel = 1
    case.record.save()
    case.harness.bridge.preparer.submit(PreparationJob(case.record.id, case.record.path, ("channel", "standin")))
    case.harness.settle()

    assert np.allclose(case.array("tomogram_full.npy"), np.abs(cube[1]))
    assert np.allclose(case.array("primary.npy"), standin(np.abs(cube[1])))
    assert case.harness.dataset(case.record.id)["pieces"]["tomogram"]["origin"] == "channel 2"


def test_a_covariance_cube_combines_its_diagonal(tmp_path):
    """npy_covariance_5d: combined is sqrt(sum_c |x[c, c]|)."""

    case     = Prepared(tmp_path, "npy", INPUTS / "npy_covariance_5d.npy")
    cube     = np.load(INPUTS / "npy_covariance_5d.npy")
    diagonal = np.stack([np.abs(cube[c, c]) for c in range(cube.shape[0])])

    assert np.allclose(case.array("tomogram_full.npy"), np.sqrt(diagonal.sum(axis=0)))
    assert case.dataset["cube"]["channels"] == cube.shape[0]


def test_one_range_line_is_prepared(tmp_path):
    """npy_one_range_line: a cube one range sample wide is a valid tomogram."""

    case = Prepared(tmp_path, "npy", INPUTS / "npy_one_range_line.npy")

    assert case.dataset["state"] == "ready"
    assert case.dataset["footprint"] == list(np.load(INPUTS / "npy_one_range_line.npy").shape[1:])


def test_a_fortran_npy_is_converted(tmp_path):
    """A Fortran-ordered .npy is converted to a C-ordered tomovis_cube.npy with the same values."""

    cube   = np.asfortranarray(np.random.default_rng(3).random((5, 7, 6)).astype(np.float32))
    source = tmp_path / "fortran.npy"
    np.save(source, cube)
    case   = Prepared(tmp_path, "npy", source)
    stored = np.load(case.folder / "data" / "tomovis_cube.npy", mmap_mode="r")

    assert not np.isfortran(stored) and np.array_equal(stored, cube)
    assert case.dataset["tomovis"]["ready"]


def test_a_2d_npy_ends_in_the_error_state(tmp_path):
    """A 2-D cube cannot be a tomogram: state error with the exact message; TomoVis itself keeps it."""

    source = tmp_path / "flat.npy"
    np.save(source, np.zeros((7, 9), dtype=np.float32))
    case   = Prepared(tmp_path, "npy", source)

    assert case.dataset["state"] == "error"
    assert case.dataset["error"] == "TomoVic tools need a 3-D cube (elevation, azimuth, range) or a multi-channel cube; flat.npy has shape 7 x 9."
    assert case.dataset["tomovis"]["ready"]


def test_slabs_equal_the_whole_array(tmp_path, monkeypatch):
    """With slabs of a few azimuth lines, the channel cube and the stand-in equal their whole-array formulas."""

    monkeypatch.setattr(CubePreparer, "SLAB_BYTES", 2048)
    case = Prepared(tmp_path, "npy", INPUTS / "npy_channels_4.npy")
    cube = np.load(INPUTS / "npy_channels_4.npy")
    full = np.sqrt((np.abs(cube) ** 2).sum(axis=0))

    assert len(case.harness.bridge.preparer.slabs(cube.shape[2], cube.nbytes // cube.shape[2])) > 3
    assert np.allclose(case.array("tomogram_full.npy"), full)
    assert np.allclose(case.array("primary.npy"), standin(full))


def test_interrupted_preparations_are_resubmitted_at_start(tmp_path):
    """A record left in state "preparing" by a stopped console is prepared from its source by the next start()."""

    stalled = BridgeHarness(tmp_path, start=False)
    stalled.bridge.preparer = StalledPreparer(stalled.workspace, stalled.logger, stalled.bridge.prepared)
    stalled.bridge.start()
    stalled.bridge.tomovis_imported("window-a", "hd5", str(INPUTS / "fusar_two_key_elev.hd5"))
    dataset_id = stalled.bridge.current["id"]

    assert stalled.dataset(dataset_id)["state"] == "preparing"

    restarted = BridgeHarness(tmp_path)
    restarted.settle()

    assert restarted.dataset(dataset_id)["state"] == "ready"
    assert restarted.dataset(dataset_id)["pieces"]["height_range"]["value"] == [-10.0, 30.0]


def test_re_importing_a_failed_dataset_retries(tmp_path):
    """An import in state error is prepared again when the same file is imported again."""

    source  = FixtureCopies(tmp_path / "user").copy(INPUTS / "fusar_two_key_elev.hd5")
    harness = BridgeHarness(tmp_path)
    record  = harness.imported("hd5", source)
    record.state = "error"
    record.save()

    assert harness.imported("hd5", source).state == "ready"


@pytest.mark.parametrize("name", ["npy_channels_2.npy", "npy_float64.npy", "npy_complex_nan_inf.npy"])
def test_other_npy_inputs_are_ready(tmp_path, name):
    """Two channels, float64 and complex with NaN and inf all end ready with a finite stand-in primary."""

    case = Prepared(tmp_path, "npy", INPUTS / name)

    assert case.dataset["state"] == "ready", case.dataset["error"]
    assert np.isfinite(case.array("primary.npy")).all()


def test_a_moved_npy_source_is_an_error_with_what_to_do(tmp_path):
    """Renaming an imported .npy breaks its tomogram link: the dataset reads as an error naming the file, not as missing pieces."""

    source  = FixtureCopies(tmp_path / "files").copy(INPUTS / "npy_real.npy", "copy.npy")
    harness = BridgeHarness(tmp_path)
    record  = harness.imported("npy", source)
    source.rename(tmp_path / "files" / "renamed.npy")
    dataset = harness.dataset(record.id)

    assert dataset["state"] == "error"
    assert dataset["error"] == f"copy.npy was moved or deleted: {source} is gone. Put the file back, or import it again in TomoVis."
    assert dataset["pieces"]["tomogram"]["problem"] == f"file moved or deleted: {source}"
    assert not dataset["tomovis"]["ready"]


def test_a_four_channel_cube_states_what_tomovis_leaves_out(tmp_path):
    """npy_channels_4: the channel piece notes that TomoVis drops channel 3 while the TomoVic tools offer all four; three channels carry no note."""

    four  = Prepared(tmp_path, "npy", INPUTS / "npy_channels_4.npy")
    three = Prepared(tmp_path / "three", "npy", INPUTS / "npy_channels_3.npy")

    assert four.dataset["channel"]["choices"] == ["combined", 0, 1, 2, 3]
    assert four.piece("channel")["note"] == "TomoVis shows channels 1, 2 and 4 of a four-channel cube and leaves out channel 3; the TomoVic tools offer all four."
    assert three.piece("channel")["note"] == ""
