"""Tests of the TomoVis link file: a FuSAR hd5 whose one dataset is stored in a .npy.

TomoVis's own FuSAR reader must read the link exactly as np.load reads the
cube, the height range and spacing must arrive as the attributes TomoVis and its
scripts read, a rewrite must never disturb a reader of the old file, and a
Fortran-ordered cube is refused.
"""

from __future__ import annotations

import h5py
import numpy as np
import pytest

from bridge.dataset_record import AtomicWriter
from bridge.tomovis_link   import TomoVisLink
from tomovis.cube_readers  import CubeReaders
from tomovis.scripts       import SlicerMatplotlibScript
from web_logger            import WebLogger


class LinkCase:
    """A cube saved in a test folder and the link writer.

    Attributes:
        cube : The saved array.
        path : Its .npy file.
        link : Link writer.
    """

    def __init__(self, folder, cube: np.ndarray) -> None:
        """Saves the cube.

        Args:
            folder : Test folder.
            cube   : Array to save.
        """

        self.cube = cube
        self.path = folder / "cube.npy"
        self.link = TomoVisLink(AtomicWriter())
        np.save(self.path, cube)

    def write(self, target, height_range=(-10.0, 30.0), spacing=(0.5, 0.75)):
        """Writes a link into the cube."""

        return self.link.write(target, self.path, height_range, spacing)


CUBES = {
    "complex_3d" : (np.random.default_rng(1).normal(size=(6, 10, 8)) + 1j * np.random.default_rng(2).normal(size=(6, 10, 8))).astype(np.complex64),
    "float_4d"   : np.random.default_rng(3).random((3, 6, 10, 8)).astype(np.float32),
    "complex_5d" : (np.random.default_rng(4).normal(size=(2, 2, 4, 5, 6)) + 1j).astype(np.complex64),
}


@pytest.mark.parametrize("name", sorted(CUBES))
def test_the_fusar_reader_reads_the_cube_through_the_link(tmp_path, name):
    """CubeReaders.fusar of the link equals np.load of the cube, with heights and spacing from the attributes."""

    case = LinkCase(tmp_path, CUBES[name])
    read = CubeReaders(WebLogger()).fusar(str(case.write(tmp_path / "link.hd5")))

    assert read.data.dtype == case.cube.dtype and np.array_equal(read.data, np.load(case.path))
    assert read.z_range == [-10.0, 30.0]
    assert (read.x_res, read.y_res) == (0.5, 0.75)


def test_the_attributes_and_the_external_storage(tmp_path):
    """One dataset 'tomogram' stored externally at the npy data offset; z limits on the dataset, spacing on the root."""

    case = LinkCase(tmp_path, CUBES["complex_3d"])
    link = case.write(tmp_path / "link.hd5")

    with h5py.File(link, "r") as h5f:
        dataset = h5f["tomogram"]
        assert list(h5f.keys()) == ["tomogram"]
        assert dataset.external[0][0] == str(case.path.resolve())
        assert dataset.external[0][1] == np.load(case.path, mmap_mode="r").offset
        assert dataset.attrs["elevation_limits"] == "[-10.0, 30.0]" and dataset.attrs["range"] == "[-10.0, 30.0]"
        assert h5f.attrs["ps_az"] == "0.5" and h5f.attrs["ps_rg"] == "0.75"
    assert link.stat().st_size < 16 * 1024


def test_unknown_heights_and_spacing(tmp_path):
    """Without a height range no z attribute is written (TomoVis uses its own default); unknown spacing is TomoVis's 1.0 x 1.0."""

    case = LinkCase(tmp_path, CUBES["float_4d"])
    link = case.write(tmp_path / "link.hd5", height_range=None, spacing=None)

    with h5py.File(link, "r") as h5f:
        assert "elevation_limits" not in h5f["tomogram"].attrs and "range" not in h5f["tomogram"].attrs
        assert h5f.attrs["ps_az"] == "1.0" and h5f.attrs["ps_rg"] == "1.0"
    assert CubeReaders(WebLogger()).fusar(str(link)).z_range is None


def test_the_slicer_script_reads_the_range(tmp_path):
    """The TomoVis Slicer script reads a scripts link: its data and the 'range' attribute."""

    case = LinkCase(tmp_path, np.abs(CUBES["complex_3d"]))
    data, _, range01, ps_az, ps_rg, _ = SlicerMatplotlibScript(WebLogger()).read(str(case.write(tmp_path / "scripts.hd5")))

    assert np.array_equal(data, case.cube)
    assert list(range01) == [-10.0, 30.0]
    assert (ps_az, ps_rg) == (0.5, 0.75)


def test_a_rewrite_replaces_the_file_and_spares_an_open_reader(tmp_path):
    """A rewrite is a new file (new inode); a reader holding the old link still reads the old attributes."""

    case = LinkCase(tmp_path, CUBES["complex_3d"])
    link = case.write(tmp_path / "link.hd5")
    old  = link.stat().st_ino

    with h5py.File(link, "r") as reader:
        case.write(tmp_path / "link.hd5", height_range=(0.0, 50.0))
        assert reader["tomogram"].attrs["range"] == "[-10.0, 30.0]"
        assert np.array_equal(reader["tomogram"][:], case.cube)

    assert link.stat().st_ino != old
    assert CubeReaders(WebLogger()).fusar(str(link)).z_range == [0.0, 50.0]
    assert [path.name for path in tmp_path.iterdir() if path.name.startswith(".")] == []


def test_a_fortran_cube_is_refused(tmp_path):
    """A Fortran-ordered .npy cannot back a link; it must be converted first."""

    case = LinkCase(tmp_path, np.asfortranarray(CUBES["float_4d"]))

    with pytest.raises(ValueError, match="Fortran order"):
        case.write(tmp_path / "link.hd5")
    assert not (tmp_path / "link.hd5").exists()
