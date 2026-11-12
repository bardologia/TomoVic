"""Server halves of TomoVis's two standalone scripts (Visualizer/Scripts).

``SlicerMatplotlibScript`` copies SlicerMatplotlib.py: the hd5 reader, the
per-column normalisation of every range slice and the matplotlib figure with
its j/k slice stepping, drawn on a WebAgg-hosted figure with matplotlib's
default keymap active. The original removed j and k from the global keymap
rcParams; the port filters j and k out of the default key handler of this
figure only, which leaves every other figure's keymap untouched. The
original's figure lived in a pyplot window, where the fullscreen keys toggle
the window and the quit keys close it through pyplot's figure registry; the
port's figure is not registered with pyplot, so the quit keys close it
through its manager directly.

``VolumeRenderingScript`` copies the data half of VolumeRendering.py
(``read_h5_volume``, ``prepare_volume`` and the thresholded second volume);
the vispy scene runs in the browser. Both scripts' prints go to the console
log. The hard-coded input path of the originals became a path the page asks
for.
"""

from __future__ import annotations

import ast

import h5py
import matplotlib as mpl
import matplotlib.cm as cm
import numpy as np
from matplotlib.backend_bases import key_press_handler

from tomovis.figure_host import TomoVisFigure, TomoVisRc
from tomovis.tools       import TomoVisTools
from web_logger          import WebLogger


class SlicerMatplotlibScript:
    """SlicerMatplotlib.py on a server figure.

    Attributes:
        logger : Console logger.
        tools  : TomoVis helpers (normalize).
    """

    REMOVED_KEYS = {"j", "k"}

    def __init__(self, logger: WebLogger) -> None:
        """Stores the logger."""

        self.logger = logger
        self.tools  = TomoVisTools()

    @staticmethod
    def parse_h5_attr(value):
        """Converts an HDF5 attribute stored as bytes or a string into a Python object."""

        if isinstance(value, bytes):
            value = value.decode()
        if isinstance(value, str):
            return ast.literal_eval(value)
        return value

    def read(self, name: str) -> tuple:
        """Reads the script's input file.

        Args:
            name : .hd5 path.

        Returns:
            (data, theta1, range01, ps_az, ps_rg, resolution).

        Raises:
            ValueError : "Invalid dataset" without a usable dataset, "No attribute 'range'." without the range attribute.
        """

        with h5py.File(name, "r") as h5f:
            keys = list(h5f.keys())

            data       = None
            theta1     = None
            range01    = None
            ps_az      = None
            ps_rg      = None
            resolution = None
            index      = None

            if len(keys) == 1:
                index = 0
                data  = h5f[keys[index]][:]
            else:
                if "tomogram" in keys:
                    index = keys.index("tomogram")
                    data  = np.abs(h5f[keys[index]][:])
                if "theta" in keys:
                    idx    = keys.index("theta")
                    theta1 = h5f[keys[idx]][:]

            if data is None:
                raise ValueError("Invalid dataset")

            if index is not None:
                attrs = h5f[keys[index]].attrs

                if "range" in attrs:
                    range01 = self.parse_h5_attr(attrs["range"])
                    range01 = np.asarray(range01, dtype=float)

                if "presum" in attrs and "resolution" in attrs:
                    resolution = self.parse_h5_attr(attrs["resolution"])

            if "ps_az" in h5f.attrs:
                ps_az = self.parse_h5_attr(h5f.attrs["ps_az"])

            if "ps_rg" in h5f.attrs:
                ps_rg = self.parse_h5_attr(h5f.attrs["ps_rg"])

        if range01 is None:
            raise ValueError("No attribute 'range'.")

        return data, theta1, range01, ps_az, ps_rg, resolution

    def normalizeSlices(self, data: np.ndarray) -> np.ndarray:
        """Normalises every column of every range slice to [0, 1], as the script's d2Norm loop.

        Args:
            data : Cube (elevation, azimuth, range).

        Returns:
            Float64 array of the cube's shape.
        """

        d2Norm = np.zeros(data.shape, dtype=float)
        for j in range(data.shape[-1]):
            d2toPlot = np.abs(np.rot90(np.abs(data[..., j]), 3))
            for i in range(d2toPlot.T.shape[-1]):
                d2Norm[:, i, j] = self.tools.normalize(d2toPlot.T[:, i], 0, 1)
        return d2Norm

    def previous_slice(self, ax) -> None:
        """Shows the previous range slice (key j)."""

        if ax.index > 0:
            ax.index -= 1
            ax.images[0].set_array(ax.volume[..., ax.index])

    def next_slice(self, ax) -> None:
        """Shows the next range slice (key k)."""

        if ax.index < ax.volume.shape[2] - 1:
            ax.index += 1
            ax.images[0].set_array(ax.volume[..., ax.index])

    def process_key(self, event) -> None:
        """The script's key handler: j and k step through the slices."""

        fig = event.canvas.figure
        ax  = fig.axes[0]
        if event.key == "j":
            self.previous_slice(ax)
        elif event.key == "k":
            self.next_slice(ax)
        fig.canvas.draw_idle()

    def filteredKeymap(self, event) -> None:
        """matplotlib's default key handler without j and k (remove_keymap_conflicts, scoped to this figure).

        key_press_handler closes a figure on keymap.quit and keymap.quit_all
        through pyplot's figure registry, which does not hold this figure;
        those keys close it through its manager, as Gcf.destroy does for the
        script's pyplot figure.
        """

        if event.key in self.REMOVED_KEYS:
            return
        key_press_handler(event, event.canvas, event.canvas.toolbar)
        if event.key in mpl.rcParams["keymap.quit"] or event.key in mpl.rcParams["keymap.quit_all"]:
            event.canvas.manager.destroy()

    @TomoVisRc.styled
    def load(self, name: str) -> TomoVisFigure:
        """Reads the file and builds the script's figure on the middle slice.

        Args:
            name : .hd5 path.

        Returns:
            The figure with the j/k handler connected.
        """

        data, theta1, range01, ps_az, ps_rg, resolution = self.read(name)
        d2Norm = self.normalizeSlices(data)

        extent = [0, d2Norm.shape[1], float(range01[0]), float(range01[1])]

        figure = TomoVisFigure("script_slicer", self.logger, keymap=True)
        figure.handlers.append(self)
        figure.canvas.mpl_disconnect(figure.manager.key_press_handler_id)
        figure.manager.key_press_handler_id = figure.canvas.mpl_connect("key_press_event", self.filteredKeymap)

        fig = figure.getFigure()
        fig.set_size_inches(8, 6)
        ax  = fig.add_subplot(111)
        fig.canvas.mpl_connect("key_press_event", self.process_key)

        ax.volume = d2Norm
        ax.index  = d2Norm.shape[2] // 2

        ax.imshow(
            d2Norm[..., ax.index],
            cmap=cm.jet,
            extent=extent,
            aspect="auto",
        )

        ax.set_xlabel("x", fontsize=20)
        ax.set_ylabel("z [m]", fontsize=20)
        ax.tick_params(labelsize=18)
        ax.set_yticks(np.linspace(extent[2], extent[3], 5))

        fig.subplots_adjust(left=0.15, bottom=0.12, right=0.98, top=0.98)
        figure.draw()
        return figure


class VolumeRenderingScript:
    """Data half of VolumeRendering.py.

    Attributes:
        console : print replacement shared with the window (TomoVisConsole).
    """

    def __init__(self, console) -> None:
        """Stores the console.

        Args:
            console : TomoVisConsole receiving the script's prints.
        """

        self.console = console

    def read_h5_volume(self, filename: str) -> tuple:
        """Reads the script's input file.

        Args:
            filename : .hd5 path.

        Returns:
            (data, theta, z_range, ps_az, ps_rg, resolution).

        Raises:
            ValueError : When no dataset with a shape exists.
        """

        data          = None
        theta         = None
        z_range       = None
        ps_az         = None
        ps_rg         = None
        resolution    = None
        dataset_index = None

        with h5py.File(filename, "r") as h5f:
            keys = list(h5f.keys())
            self.console.print("HDF5 keys:", keys)

            if len(keys) == 1:
                dataset_index = 0
                data          = h5f[keys[dataset_index]][:]
            else:
                if "tomogram" in keys:
                    dataset_index = keys.index("tomogram")
                    data          = np.abs(h5f[keys[dataset_index]][:])
                else:
                    for i, key in enumerate(keys):
                        if hasattr(h5f[key], "shape"):
                            dataset_index = i
                            data          = np.abs(h5f[key][:])
                            break

                if "theta" in keys:
                    theta_index = keys.index("theta")
                    theta       = h5f[keys[theta_index]][:]

            if data is None:
                raise ValueError("No valid volume dataset was found in the HDF5 file.")

            if dataset_index is not None:
                attrs = h5f[keys[dataset_index]].attrs

                if "range" in attrs:
                    z_range = SlicerMatplotlibScript.parse_h5_attr(attrs["range"])
                    z_range = np.asarray(z_range, dtype=float)

                if "presum" in attrs and "resolution" in attrs:
                    resolution = SlicerMatplotlibScript.parse_h5_attr(attrs["resolution"])

            if "ps_az" in h5f.attrs:
                ps_az = SlicerMatplotlibScript.parse_h5_attr(h5f.attrs["ps_az"])

            if "ps_rg" in h5f.attrs:
                ps_rg = SlicerMatplotlibScript.parse_h5_attr(h5f.attrs["ps_rg"])

        return data, theta, z_range, ps_az, ps_rg, resolution

    def prepare_volume(self, data) -> np.ndarray:
        """Turns the data into a min-max normalised float32 volume (first channel of a 4-D cube).

        Raises:
            ValueError : When the volume is not 3-D.
        """

        volume = np.array(data)

        if np.iscomplexobj(volume):
            volume = np.abs(volume)

        if volume.ndim == 4:
            volume = volume[0]

        if volume.ndim != 3:
            raise ValueError(f"Expected a 3D volume, got shape={volume.shape}")

        volume = np.nan_to_num(volume, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)

        vmin = float(volume.min())
        vmax = float(volume.max())

        self.console.print("Original shape:", volume.shape)
        self.console.print("Min / max:", vmin, vmax)

        if vmax > vmin:
            volume = (volume - vmin) / (vmax - vmin)
        else:
            volume[:] = 0.0

        return volume

    def load(self, filename: str) -> dict:
        """Runs the script's start-up: read, prepare both volumes, print the summary.

        Args:
            filename : .hd5 path.

        Returns:
            {"volume_1", "volume_2" (float32 arrays), "z_range", "ps_az", "ps_rg", "resolution", "shape"}.
        """

        data, theta, z_range, ps_az, ps_rg, resolution = self.read_h5_volume(filename)
        volume_1 = self.prepare_volume(data)
        volume_2 = (volume_1 > 0.4).astype(np.float32)

        self.console.print("Volume 1 shape:", volume_1.shape)
        self.console.print("Volume 2 shape:", volume_2.shape)
        if z_range is not None:
            self.console.print("Vertical range:", z_range)
        if ps_az is not None:
            self.console.print("Azimuth sampling:", ps_az)
        if ps_rg is not None:
            self.console.print("Range sampling:", ps_rg)
        if resolution is not None:
            self.console.print("Resolution:", resolution)

        return {
            "volume_1"   : volume_1,
            "volume_2"   : volume_2,
            "shape"      : list(volume_1.shape),
            "z_range"    : None if z_range is None else [float(value) for value in z_range],
            "ps_az"      : None if ps_az is None else float(ps_az),
            "ps_rg"      : None if ps_rg is None else float(ps_rg),
            "resolution" : None if resolution is None else np.asarray(resolution).tolist(),
        }
