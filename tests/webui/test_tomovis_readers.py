"""Tests of the four TomoVis import readers and their window integration.

Every fixture input is read; the RAT reader (with the numpy-2 fixes of E-006)
returns the cube the original read with legacy numpy names restored; RAT 1.0
files in both byte orders are read; hd5 attributes follow D-2; failed reads
follow D-3: an ``Import error`` message and the previous cube kept.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import struct
import warnings

import h5py
import numpy as np
import pytest

from tests.webui.conftest import REPO_ROOT
from tomovis.cube_readers  import CubeReaders, H5Attributes
from tomovis.window        import TomoVisWindow
from web_logger            import WebLogger

FIXTURES = REPO_ROOT / "tests" / "webui" / "fixtures" / "tomovis"
INPUTS   = FIXTURES / "inputs"


def sha1(array: np.ndarray) -> str:
    """Hashes a cube as the goldens' data_summary does."""

    digest = hashlib.sha1()
    digest.update(str(array.dtype).encode())
    digest.update(str(array.shape).encode())
    digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


def golden_summary(scenario: str) -> dict:
    """data_summary of the loaded cube after a golden's import step."""

    doc = json.loads(gzip.open(FIXTURES / "goldens" / f"{scenario}.json.gz").read())
    return doc["steps"][1]["state"]["attributes"]["data_summary"]


class ImportDriver:
    """Imports files into a window through the API events.

    Attributes:
        window : Window under test.
    """

    ACTIONS = {"hd5": "openFUSAR", "rat": "openRAT", "h5": "openUAVSAR", "npy": "openNpy"}

    def __init__(self) -> None:
        """Opens a fresh window."""

        self.window = TomoVisWindow(WebLogger("tomovis-test"))
        self.window.drain()

    def load(self, kind: str, path) -> list[dict]:
        """Imports one file and returns the dialogs the import produced after the file dialog."""

        self.window.handle({"type": "trigger", "widget": self.ACTIONS[kind]})
        token = self.window.dialogs.pendingToken()
        self.window.drain()
        self.window.handle({"type": "dialog_result", "token": token, "accepted": True, "path": str(path)})
        output = self.window.drain()
        assert output.slot_errors == []
        return output.dialogs


@pytest.fixture
def readers() -> CubeReaders:
    """Readers with a test logger."""

    return CubeReaders(WebLogger("tomovis-test"))


@pytest.mark.parametrize("name, shape, z_range, x_res, y_res", [
    ("fusar_two_key_elev.hd5", (16, 32, 24), [-10.0, 30.0], 0.5, 0.75),
    ("fusar_one_key_range.hd5", (16, 32, 24), [0.0, 45.0], None, None),
    ("fusar_both_attrs.hd5", (8, 12, 10), [-5.0, 15.0], None, None),
    ("fusar_no_attrs.hd5", (8, 12, 10), None, None, None),
    ("fusar_three_keys.hd5", (8, 12, 10), [-1.0, 1.0], None, None),
    ("fusar_bytes_attrs.hd5", (8, 12, 10), [-2.5, 7.5], 0.25, 1.5),
    ("fusar_numeric_attrs.hd5", (8, 12, 10), [-1.0, 4.0], 0.3, None),
])
def test_fusar_reader(readers, name, shape, z_range, x_res, y_res):
    """The dataset is key 1 (key 0 alone); elevation_limits wins over range; spacings come from the root (D-2 for bytes and numbers)."""

    cube = readers.fusar(INPUTS / name)

    assert cube.data.shape == shape
    assert (None if cube.z_range is None else [float(value) for value in cube.z_range]) == z_range
    assert cube.x_res == (None if x_res is None else pytest.approx(x_res))
    assert cube.y_res == (None if y_res is None else pytest.approx(y_res))


def test_uavsar_reader_swaps_the_first_two_axes(readers):
    """The third key, with axes 0 and 1 swapped."""

    with h5py.File(INPUTS / "uavsar_three_keys.h5", "r") as h5f:
        raw = h5f["tomo"][:]

    assert np.array_equal(readers.uavsar(INPUTS / "uavsar_three_keys.h5"), np.rollaxis(raw, 1, 0))


@pytest.mark.parametrize("name", ["npy_real.npy", "npy_float64.npy", "npy_complex_nan_inf.npy", "npy_one_range_line.npy", "npy_channels_2.npy", "npy_channels_3.npy", "npy_channels_4.npy", "npy_covariance_5d.npy"])
def test_npy_reader(readers, name):
    """np.load with numpy's defaults."""

    assert np.array_equal(readers.npy(INPUTS / name), np.load(INPUTS / name), equal_nan=True)


def test_rat_reader_matches_the_original_with_legacy_numpy(readers):
    """E-006: the RAT 2.0 fixture reads back as the original read it with np.int restored (same SHA-1)."""

    cube = readers.rat(INPUTS / "rat_complex.rat")

    assert cube.shape == (12, 20, 16) and cube.dtype == np.complex64
    assert sha1(cube) == golden_summary("import_rat_legacy_numpy")["sha1"]


@pytest.mark.parametrize("big_endian", [False, True])
def test_rat_version_one_files_in_both_byte_orders(readers, tmp_path, big_endian):
    """A RAT 1.0 header (ndim, IDL shape, var, rattype, padding, 80-byte info) and its data, little endian or XDR."""

    cube   = np.arange(3 * 4 * 5, dtype=np.float32).reshape(3, 4, 5)
    order  = ">" if big_endian else "<"
    shape  = list(cube.shape[::-1])
    header = struct.pack(f"{order}i", 3) + struct.pack(f"{order}3i", *shape) + struct.pack(f"{order}2i", 4, 0)
    header = header + b"\0" * (16 if big_endian else 12) + b"info".ljust(80, b"\0")
    path   = tmp_path / "v1.rat"
    path.write_bytes(header + cube.astype(f"{order}f4").tobytes())

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        read = readers.rat(path)

    assert np.array_equal(read, cube)


def test_unrecognised_rat_file_raises(readers, tmp_path):
    """A file that is neither RAT version raises ValueError, which the import reports (D-3)."""

    path = tmp_path / "junk.rat"
    path.write_bytes(struct.pack("<i", 100) + b"\0" * 64)

    with pytest.raises(ValueError, match="format not recognised"):
        readers.rat(path)


def test_h5_attribute_parser():
    """Bytes are decoded, strings evaluated as literals, other values passed through (D-2)."""

    assert H5Attributes.parse(b"[-2.5, 7.5]") == [-2.5, 7.5]
    assert H5Attributes.parse("0.5") == 0.5
    assert H5Attributes.parse(0.3) == 0.3


def test_imports_through_the_window_follow_the_menu_flow():
    """Each import asks for its file with its own filter and loads the cube into the views."""

    driver = ImportDriver()
    driver.window.handle({"type": "trigger", "widget": "openRAT"})
    request = driver.window.drain().dialogs[0]

    assert (request["kind"], request["title"], request["filters"]) == ("file", "Open File", ["RAT file (*.rat)"])

    driver.window.handle({"type": "dialog_result", "token": request["token"], "accepted": True, "path": str(INPUTS / "rat_complex.rat")})
    driver.window.drain()

    assert driver.window.img.shape == (20, 16)
    assert driver.window.z_range == [0.0, 15.0]


class BrokenInputs:
    """Writes files every reader fails on."""

    def write(self, case: str, folder) -> tuple[str, object]:
        """Writes one broken input.

        Args:
            case   : "group" (hd5 with a group at key 1), "two_keys" (h5 without a third key), "pickle" (npy needing pickles), "rat" (unknown format), "missing" (no file).
            folder : Directory for the file.

        Returns:
            (import kind, path).
        """

        if case == "group":
            path = folder / "group.hd5"
            with h5py.File(path, "w") as h5f:
                h5f.create_dataset("a_data", data=np.ones((2, 2, 2)))
                h5f.create_group("b_group")
            return "hd5", path
        if case == "two_keys":
            path = folder / "two.h5"
            with h5py.File(path, "w") as h5f:
                h5f.create_dataset("a", data=np.ones((2, 2, 2)))
                h5f.create_dataset("b", data=np.ones((2, 2, 2)))
            return "h5", path
        if case == "pickle":
            path = folder / "objects.npy"
            np.save(path, np.array([object()], dtype=object), allow_pickle=True)
            return "npy", path
        if case == "rat":
            path = folder / "junk.rat"
            path.write_bytes(struct.pack("<i", -77) + b"\0" * 64)
            return "rat", path
        return "npy", folder / "missing.npy"


@pytest.mark.parametrize("case", ["group", "two_keys", "pickle", "rat", "missing"])
def test_failed_import_reports_and_keeps_the_previous_cube(tmp_path, case):
    """D-3: a read failure shows Import error and leaves the loaded cube, views and controls as they were."""

    driver = ImportDriver()
    driver.load("npy", INPUTS / "npy_real.npy")
    before     = driver.window.snapshot()
    kind, path = BrokenInputs().write(case, tmp_path)

    dialogs = driver.load(kind, path)

    assert [(dialog["level"], dialog["title"]) for dialog in dialogs] == [("critical", "Import error")]
    assert dialogs[0]["text"].startswith("Could not import file:\n")
    assert driver.window.data.shape == (16, 32, 24)
    assert driver.window.snapshot()["controls"] == before["controls"]
    assert driver.window.snapshot()["attributes"] == before["attributes"]


def test_cancelled_import_stops_play_and_changes_nothing():
    """F-016: the timer stops before the dialog, and a cancel loads nothing."""

    driver = ImportDriver()
    driver.load("npy", INPUTS / "npy_real.npy")
    for event in ({"type": "check", "widget": "tab1ChkBox", "checked": True}, {"type": "click", "widget": "tab1PlayButton"}):
        driver.window.handle(event)
    assert driver.window.tab1Timer.isActive()

    driver.window.handle({"type": "trigger", "widget": "openFUSAR"})

    assert not driver.window.tab1Timer.isActive()

    driver.window.handle({"type": "dialog_result", "token": driver.window.dialogs.pendingToken(), "accepted": False})

    assert driver.window.data.shape == (16, 32, 24)
