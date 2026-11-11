"""Deterministic input cubes in every format the original TomoVis imports.

The synthetic cubes are small, seeded and shaped like the tomograms TomoVis
reads: axis 0 is elevation, axis 1 azimuth and axis 2 range (the code slices
the top view over axis 0 and the ROI over axes 1 and 2), multi-channel cubes
put the channel first and the covariance cube puts the two matrix axes first.
The RAT file is written with STEtools' own writer, which needs three numpy
names removed in numpy 2 (``np.ctypeslib.array``, ``np.product``,
``np.int``); NumpyLegacyNames installs them only for the duration of a call.
The realistic cube is a crop of the DLR-TomoSAR test tomogram for visual
checks and is never committed.
"""

from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np


class NumpyLegacyNames:
    """Context manager that restores the numpy 1.x names STEtools calls.

    Attributes:
        installed : Names this instance added to numpy, removed again on exit.
    """

    NAMES = ("int", "product", "ctypeslib.array")

    def __init__(self) -> None:
        """Starts with nothing installed."""

        self.installed = []

    def __enter__(self) -> "NumpyLegacyNames":
        """Adds ``np.int``, ``np.product`` and ``np.ctypeslib.array`` when numpy lacks them.

        Returns:
            This context manager.
        """

        if not hasattr(np, "int"):
            np.int = int
            self.installed.append("int")
        if not hasattr(np, "product"):
            np.product = np.prod
            self.installed.append("product")
        if not hasattr(np.ctypeslib, "array"):
            np.ctypeslib.array = np.array
            self.installed.append("ctypeslib.array")
        return self

    def __exit__(self, *exc_info) -> None:
        """Removes every name this instance added."""

        for name in self.installed:
            if name == "ctypeslib.array":
                del np.ctypeslib.array
            else:
                delattr(np, name)
        self.installed = []


class SyntheticCube:
    """Seeded tomogram-like cube with a ground layer, a canopy layer and noise.

    Attributes:
        seed  : Seed of the numpy generator that draws the noise and phases.
        shape : Cube shape (n_elevation, n_azimuth, n_range).
    """

    def __init__(self, seed: int, shape: tuple[int, int, int]) -> None:
        """Stores the seed and the cube shape.

        Args:
            seed  : Seed of the numpy generator.
            shape : Cube shape (n_elevation, n_azimuth, n_range).
        """

        self.seed  = seed
        self.shape = shape

    def amplitude(self) -> np.ndarray:
        """Builds the real amplitude cube.

        Returns:
            Float32 array of ``shape`` with a sinuous ground return, a patchy canopy return about 40 % of the column above it and uniform noise of 0.05.
        """

        n_z, n_az, n_rg = self.shape
        rng             = np.random.default_rng(self.seed)

        z       = np.arange(n_z, dtype=np.float64)[:, None, None]
        azimuth = np.arange(n_az, dtype=np.float64)[None, :, None]
        rng_ax  = np.arange(n_rg, dtype=np.float64)[None, None, :]

        ground  = n_z * 0.25 + 1.5 * np.sin(2.0 * np.pi * azimuth / n_az) + 1.0 * np.cos(2.0 * np.pi * rng_ax / n_rg)
        canopy  = ground + n_z * 0.4 + 1.0 * np.sin(4.0 * np.pi * (azimuth + rng_ax) / (n_az + n_rg))
        forest  = (np.sin(2.0 * np.pi * azimuth / (n_az / 2.0)) * np.cos(2.0 * np.pi * rng_ax / (n_rg / 1.5)) > -0.2).astype(np.float64)
        weights = 0.5 + rng.random((1, n_az, n_rg))

        cube = np.exp(-0.5 * ((z - ground) / 0.8) ** 2) * weights
        cube = cube + 0.6 * forest * np.exp(-0.5 * ((z - canopy) / 1.5) ** 2)
        cube = cube + 0.05 * rng.random(self.shape)
        return cube.astype(np.float32)

    def complex(self) -> np.ndarray:
        """Builds the complex cube from the amplitude and a seeded random phase.

        Returns:
            Complex64 array of ``shape`` whose magnitude equals amplitude().
        """

        amplitude = self.amplitude().astype(np.float64)
        phase     = np.random.default_rng(self.seed + 1000).uniform(-np.pi, np.pi, self.shape)
        return (amplitude * np.exp(1j * phase)).astype(np.complex64)

    def channels(self, count: int) -> np.ndarray:
        """Stacks ``count`` amplitude cubes drawn with consecutive seeds and different gains.

        Args:
            count : Number of channels.

        Returns:
            Float32 array (count, n_elevation, n_azimuth, n_range).
        """

        stack = []
        for index in range(count):
            cube = SyntheticCube(self.seed + 17 * (index + 1), self.shape).amplitude()
            stack.append(cube * np.float32(1.0 + 0.5 * index))
        return np.stack(stack).astype(np.float32)

    def covariance(self, order: int) -> np.ndarray:
        """Builds a Hermitian covariance-like cube whose diagonal holds squared channel amplitudes.

        Args:
            order : Number of polarimetric channels, the size of each matrix.

        Returns:
            Complex64 array (order, order, n_elevation, n_azimuth, n_range).
        """

        channels = self.channels(order).astype(np.float64)
        phases   = np.random.default_rng(self.seed + 2000).uniform(-np.pi, np.pi, (order,) + self.shape)
        fields   = channels * np.exp(1j * phases)
        matrix   = np.einsum("i...,j...->ij...", fields, np.conj(fields))
        return matrix.astype(np.complex64)


class FixtureWriter:
    """Writes the committed input fixtures for every TomoVis import path.

    Attributes:
        root     : Directory receiving the input files.
        ste_io   : The original STEtools module, whose srat writes the RAT fixture.
        manifest : File name to description, shape, dtype and attributes of every fixture written.
    """

    BASE_SHAPE  = (16, 32, 24)
    SMALL_SHAPE = (8, 12, 10)
    MULTI_SHAPE = (10, 24, 16)
    COV_SHAPE   = (8, 16, 12)

    def __init__(self, root: Path, ste_io) -> None:
        """Creates the output directory.

        Args:
            root   : Directory receiving the input files.
            ste_io : The imported ``Visualizer.ste_io`` module of the original app.
        """

        self.root     = root
        self.ste_io   = ste_io
        self.manifest = {}
        self.root.mkdir(parents=True, exist_ok=True)

    def _record(self, name: str, description: str, array: np.ndarray, attributes: dict) -> None:
        """Adds one fixture to the manifest.

        Args:
            name        : File name inside ``root``.
            description : What the fixture exercises.
            array       : The cube as stored in the file.
            attributes  : Attributes written next to the cube, as strings.
        """

        self.manifest[name] = {
            "description" : description,
            "shape"       : list(array.shape),
            "dtype"       : str(array.dtype),
            "attributes"  : attributes,
        }

    def write_fusar(self) -> None:
        """Writes the FuSAR .hd5 variants: attribute sets, key counts and attribute types."""

        base  = SyntheticCube(11, self.BASE_SHAPE)
        small = SyntheticCube(12, self.SMALL_SHAPE)

        path = self.root / "fusar_two_key_elev.hd5"
        with h5py.File(path, "w") as h5f:
            h5f.create_dataset("theta", data=np.linspace(0.0, 1.0, self.BASE_SHAPE[0], dtype=np.float32))
            cube = base.complex()
            dset = h5f.create_dataset("tomogram", data=cube)
            dset.attrs["elevation_limits"] = "[-10.0, 30.0]"
            h5f.attrs["ps_az"] = "0.5"
            h5f.attrs["ps_rg"] = "0.75"
        self._record(path.name, "two keys (theta, tomogram), complex64, elevation_limits on the dataset, ps_az and ps_rg strings on the file", cube, {"tomogram.elevation_limits": "[-10.0, 30.0]", "ps_az": "0.5", "ps_rg": "0.75"})

        path = self.root / "fusar_one_key_range.hd5"
        with h5py.File(path, "w") as h5f:
            cube = SyntheticCube(13, self.BASE_SHAPE).amplitude()
            dset = h5f.create_dataset("tomogram", data=cube)
            dset.attrs["range"] = "[0.0, 45.0]"
        self._record(path.name, "one key, float32, range attribute only, no pixel spacings", cube, {"tomogram.range": "[0.0, 45.0]"})

        path = self.root / "fusar_both_attrs.hd5"
        with h5py.File(path, "w") as h5f:
            cube = small.amplitude()
            dset = h5f.create_dataset("tomogram", data=cube)
            dset.attrs["elevation_limits"] = "[-5.0, 15.0]"
            dset.attrs["range"]            = "[100.0, 200.0]"
        self._record(path.name, "elevation_limits and range both present: elevation_limits wins", cube, {"tomogram.elevation_limits": "[-5.0, 15.0]", "tomogram.range": "[100.0, 200.0]"})

        path = self.root / "fusar_no_attrs.hd5"
        with h5py.File(path, "w") as h5f:
            cube = small.amplitude()
            h5f.create_dataset("tomogram", data=cube)
        self._record(path.name, "no z attributes: default z range [0, shape[-1] - 1]", cube, {})

        path = self.root / "fusar_three_keys.hd5"
        with h5py.File(path, "w") as h5f:
            cube = SyntheticCube(14, self.SMALL_SHAPE).amplitude()
            h5f.create_dataset("a_coherence", data=np.ones(4, dtype=np.float32))
            dset = h5f.create_dataset("b_tomogram", data=cube)
            dset.attrs["range"] = "[-1.0, 1.0]"
            h5f.create_dataset("c_theta", data=np.zeros(4, dtype=np.float32))
        self._record(path.name, "three keys: the importer always takes key index 1 (b_tomogram)", cube, {"b_tomogram.range": "[-1.0, 1.0]"})

        path = self.root / "fusar_bytes_attrs.hd5"
        with h5py.File(path, "w") as h5f:
            cube = SyntheticCube(15, self.SMALL_SHAPE).amplitude()
            dset = h5f.create_dataset("tomogram", data=cube)
            dset.attrs["elevation_limits"] = np.bytes_(b"[-2.5, 7.5]")
            h5f.attrs["ps_az"] = np.bytes_(b"0.25")
            h5f.attrs["ps_rg"] = np.bytes_(b"1.5")
        self._record(path.name, "attributes stored as fixed-length byte strings (h5py returns numpy bytes)", cube, {"tomogram.elevation_limits": "b'[-2.5, 7.5]'", "ps_az": "b'0.25'", "ps_rg": "b'1.5'"})

        path = self.root / "fusar_numeric_attrs.hd5"
        with h5py.File(path, "w") as h5f:
            cube = SyntheticCube(16, self.SMALL_SHAPE).amplitude()
            dset = h5f.create_dataset("tomogram", data=cube)
            dset.attrs["elevation_limits"] = np.array([-1.0, 4.0])
            h5f.attrs["ps_az"] = 0.3
        self._record(path.name, "numeric (not string) attributes: eval() raises TypeError in the original", cube, {"tomogram.elevation_limits": "float64 array [-1.0, 4.0]", "ps_az": "float 0.3"})

    def write_uavsar(self) -> None:
        """Writes the UAVSAR .h5 fixture with three keys and the cube stored azimuth first."""

        cube   = SyntheticCube(21, self.BASE_SHAPE).amplitude()
        stored = np.ascontiguousarray(np.swapaxes(cube, 0, 1))
        path   = self.root / "uavsar_three_keys.h5"
        with h5py.File(path, "w") as h5f:
            h5f.create_dataset("lat", data=np.linspace(47.0, 47.1, 4))
            h5f.create_dataset("lon", data=np.linspace(11.0, 11.1, 4))
            h5f.create_dataset("tomo", data=stored)
        self._record(path.name, "three keys (lat, lon, tomo); the importer takes key index 2 and applies np.rollaxis(x, 1, 0)", stored, {})

    def write_npy(self) -> None:
        """Writes the .npy fixtures: real, float64, complex with NaN and inf, multi-channel, covariance, one range line."""

        cube = SyntheticCube(31, self.BASE_SHAPE).amplitude()
        np.save(self.root / "npy_real.npy", cube)
        self._record("npy_real.npy", "float32 single channel", cube, {})

        cube = SyntheticCube(32, self.SMALL_SHAPE).amplitude().astype(np.float64)
        np.save(self.root / "npy_float64.npy", cube)
        self._record("npy_float64.npy", "float64 single channel", cube, {})

        cube = SyntheticCube(33, (12, 20, 16)).complex()
        cube[3, 5, 7]   = complex(np.nan, 0.0)
        cube[6, 2, 9]   = complex(np.inf, 0.0)
        cube[8, 11, 3]  = complex(0.0, -np.inf)
        cube[1, 15, 12] = complex(np.nan, 1.0)
        cube[4, 4, :]   = complex(np.nan, np.nan)
        np.save(self.root / "npy_complex_nan_inf.npy", cube)
        self._record("npy_complex_nan_inf.npy", "complex64 with NaN, +inf and -inf samples, one azimuth-range line all NaN", cube, {})

        cube = SyntheticCube(34, (6, 10, 1)).amplitude()
        np.save(self.root / "npy_one_range_line.npy", cube)
        self._record("npy_one_range_line.npy", "shape[-1] == 1: the slice slider stays at 0 and nothing is drawn on load", cube, {})

        for count in (2, 3, 4):
            cube = SyntheticCube(40 + count, self.MULTI_SHAPE).channels(count)
            name = f"npy_channels_{count}.npy"
            np.save(self.root / name, cube)
            self._record(name, f"{count} channels, float32, channel axis first", cube, {})

        cube = SyntheticCube(51, self.COV_SHAPE).covariance(3)
        np.save(self.root / "npy_covariance_5d.npy", cube)
        self._record("npy_covariance_5d.npy", "5-D 3x3 covariance-like cube; TomoVis keeps sqrt of the diagonal as 3 channels", cube, {})

    def write_rat(self) -> None:
        """Writes the RAT fixture with STEtools' own srat, under the numpy legacy names it needs."""

        cube = SyntheticCube(61, (12, 20, 16)).complex()
        path = self.root / "rat_complex.rat"
        with NumpyLegacyNames():
            self.ste_io.srat(str(path), cube)
        self._record(path.name, "complex64 RAT 2.0 file written by ste_io.srat (1000-byte header, C-order payload)", cube, {})

    def write_manifest(self) -> Path:
        """Writes ``manifest.json`` describing every fixture.

        Returns:
            Path of the manifest.
        """

        path = self.root / "manifest.json"
        path.write_text(json.dumps(self.manifest, indent=2, sort_keys=True) + "\n")
        return path

    def run(self) -> dict:
        """Writes every input fixture and the manifest.

        Returns:
            The manifest, file name to description, shape, dtype and attributes.
        """

        self.write_fusar()
        self.write_uavsar()
        self.write_npy()
        self.write_rat()
        self.write_manifest()
        return self.manifest


class RealisticCube:
    """Crops the DLR-TomoSAR test tomogram into FuSAR-style files for visual checks.

    The source cube is (elevation, azimuth, range) complex64 over a -20 m to 80 m
    height range, which is already TomoVis's axis order. The pseudo-RGB cube
    stacks three azimuth windows of the same scene as channels; it only serves
    the look of the RGB views, not any physical meaning.

    Attributes:
        source : Path of ``tomogram_full.npy`` in the DLR-TomoSAR test data.
        root   : Directory receiving the cropped files (gitignored).
    """

    HEIGHT_RANGE = "[-20.0, 80.0]"
    PS_AZ        = "0.39138419083172127"
    PS_RG        = "0.5994167613220001"
    AZ_WINDOWS   = ((300, 700), (0, 400), (600, 1000))
    RG_WINDOW    = (150, 350)

    def __init__(self, source: Path, root: Path) -> None:
        """Stores the paths and creates the output directory.

        Args:
            source : Path of the DLR-TomoSAR ``tomogram_full.npy``.
            root   : Directory receiving the cropped files.
        """

        self.source = source
        self.root   = root
        self.root.mkdir(parents=True, exist_ok=True)

    def write_single(self) -> Path:
        """Writes the single-channel FuSAR .hd5 crop with height range and pixel spacings.

        Returns:
            Path of the written file.
        """

        cube   = np.load(self.source, mmap_mode="r")
        az, rg = self.AZ_WINDOWS[0], self.RG_WINDOW
        crop   = np.ascontiguousarray(cube[:, az[0]:az[1], rg[0]:rg[1]])
        path   = self.root / "realistic_traun_hv.hd5"

        with h5py.File(path, "w") as h5f:
            dset = h5f.create_dataset("tomogram", data=crop)
            dset.attrs["range"] = self.HEIGHT_RANGE
            h5f.attrs["ps_az"] = self.PS_AZ
            h5f.attrs["ps_rg"] = self.PS_RG
        return path

    def write_rgb(self) -> Path:
        """Writes the three-channel pseudo-RGB .npy built from three azimuth windows.

        Returns:
            Path of the written file.
        """

        cube   = np.load(self.source, mmap_mode="r")
        rg     = self.RG_WINDOW
        stack  = [np.abs(cube[:, az[0]:az[1], rg[0]:rg[1]]).astype(np.float32) for az in self.AZ_WINDOWS]
        path   = self.root / "realistic_pseudo_rgb.npy"
        np.save(path, np.stack(stack))
        return path

    def run(self) -> dict:
        """Writes both realistic cubes.

        Returns:
            Mapping with the "single" and "rgb" file paths.
        """

        return {"single": self.write_single(), "rgb": self.write_rgb()}
