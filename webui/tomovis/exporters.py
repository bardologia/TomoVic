"""Server halves of pyqtgraph's Export dialog on the TomoVis page.

The browser renders images, SVG and CSV the way pyqtgraph's exporters do and
sends the result here to be written on the server, where TomoVis wrote it
(decision D-4). ``Hdf5PlotExporter`` copies pyqtgraph's HDF5Exporter and
``MatplotlibPlotExporter`` copies the drawing of pyqtgraph's
MatplotlibExporter into a server figure that the browser shows as the
"Matplotlib Window".
"""

from __future__ import annotations

import io
from pathlib import Path

import h5py
import numpy
from PIL import Image

from tomovis.events      import TomoVisEventError
from tomovis.figure_host import TomoVisFigure


class ExportWriter:
    """Writes exported images and text files.

    Attributes:
        PILLOW_FORMATS : Lower-case extensions written by re-encoding the PNG with Pillow, to Pillow's format names.
    """

    PILLOW_FORMATS = {".jpg": "JPEG", ".jpeg": "JPEG", ".tif": "TIFF", ".tiff": "TIFF", ".bmp": "BMP", ".ppm": "PPM", ".webp": "WEBP"}

    def target(self, path: str) -> Path:
        """Checks a target path.

        Raises:
            TomoVisEventError : If the path is not absolute or its directory does not exist.
        """

        target = Path(path)
        if not target.is_absolute():
            raise TomoVisEventError(f"'{path}' is not an absolute path")
        if not target.parent.is_dir():
            raise TomoVisEventError(f"the directory of '{path}' does not exist")
        return target

    def writeImage(self, path: str, png: bytes) -> Path:
        """Writes an image in the format its extension implies, as QImage.save does.

        PNG is written as received; other formats Pillow knows are re-encoded
        from the PNG, with alpha dropped for JPEG.

        Args:
            path : Absolute target path.
            png  : PNG bytes rendered by the browser.

        Returns:
            The written path.

        Raises:
            TomoVisEventError : For an unknown extension (QImage.save returns False there) or an unwritable path.
        """

        target = self.target(path)
        suffix = target.suffix.lower()
        if suffix == ".png":
            target.write_bytes(png)
            return target
        if suffix not in self.PILLOW_FORMATS:
            raise TomoVisEventError(f"cannot write an image with the extension '{target.suffix}'")

        image = Image.open(io.BytesIO(png))
        if self.PILLOW_FORMATS[suffix] in ("JPEG", "BMP", "PPM"):
            image = image.convert("RGB")
        image.save(target, format=self.PILLOW_FORMATS[suffix])
        return target

    def writeBytes(self, path: str, data: bytes) -> Path:
        """Writes raw bytes (CSV and SVG text).

        Args:
            path : Absolute target path.
            data : File contents.

        Returns:
            The written path.
        """

        target = self.target(path)
        target.write_bytes(data)
        return target


class Hdf5PlotExporter:
    """pyqtgraph's HDF5Exporter for the ImageView ROI plot."""

    COLUMN_MODES = ('(x,y) per plot', '(x,y,y,y) for all plots')

    def export(self, fileName: str, dsname: str, columnMode: str, curves: list[dict]) -> None:
        """Appends the curves to an HDF5 file as HDF5Exporter.export does.

        Args:
            fileName   : Absolute target path; the file is opened in append mode.
            dsname     : Dataset (or group, for ragged curves) name.
            columnMode : "(x,y) per plot" or "(x,y,y,y) for all plots".
            curves     : [{"x": [...], "y": [...], "name": str or None}] in plot order.

        Raises:
            TomoVisEventError : For an unknown column mode or no curves.
        """

        if columnMode not in self.COLUMN_MODES:
            raise TomoVisEventError(f"unknown column mode '{columnMode}'")
        if not curves:
            raise TomoVisEventError("the plot has no curves")

        fd         = h5py.File(fileName, 'a')
        data       = []
        appendAllX = columnMode == '(x,y) per plot'

        len_first = len(curves[0]["x"])
        ragged    = any(len(curve["x"]) != len_first for curve in curves)
        if ragged:
            dgroup = fd.create_group(dsname)
            for i, curve in enumerate(curves):
                fdata = numpy.array([curve["x"], curve["y"]]).astype('double')
                cname = curve.get("name") if curve.get("name") is not None else str(i)
                dgroup.create_dataset(cname, data=fdata)
        else:
            for i, curve in enumerate(curves):
                if appendAllX or i == 0:
                    data.append(curve["x"])
                data.append(curve["y"])
            fdata = numpy.array(data).astype('double')
            fd.create_dataset(dsname, data=fdata)
        fd.close()


class MatplotlibPlotExporter:
    """pyqtgraph's MatplotlibExporter drawing a plot's curves into a matplotlib figure.

    Attributes:
        SYMBOLS : pyqtgraph symbol name to matplotlib marker.
    """

    SYMBOLS = {
        'o'           : 'o',
        's'           : 's',
        't'           : 'v',
        't1'          : '^',
        't2'          : '>',
        't3'          : '<',
        'd'           : 'd',
        '+'           : 'P',
        'x'           : 'X',
        'p'           : 'p',
        'h'           : 'h',
        'star'        : '*',
        'arrow_up'    : 6,
        'arrow_right' : 5,
        'arrow_down'  : 7,
        'arrow_left'  : 4,
        'crosshair'   : 'o',
        '|'           : '|',
        '_'           : '_'
    }

    def cleanAxes(self, axl) -> None:
        """Hides the top and right spines and keeps ticks at the bottom (MatplotlibExporter.cleanAxes)."""

        if type(axl) is not list:
            axl = [axl]
        for ax in axl:
            if ax is None:
                continue
            for loc, spine in ax.spines.items():
                if loc in ['left', 'bottom']:
                    pass
                elif loc in ['right', 'top']:
                    spine.set_color('none')
                else:
                    raise ValueError('Unknown spine location: %s' % loc)
                ax.xaxis.set_ticks_position('bottom')

    def export(self, mpw: TomoVisFigure, plot: dict) -> None:
        """Draws the plot into the export figure.

        Args:
            mpw  : The "Matplotlib Window" figure.
            plot : {"curves": [{"x", "y", "pen": {"color": [r, g, b, a] in 0..1, "width", "style": "solid" | "none"}, "symbol", "symbolSize", "symbolPen": [r, g, b, a], "symbolBrush": [r, g, b, a], "fillLevel", "fillBrush"}], "xlabel", "ylabel", "title", "xrange": [lo, hi], "yrange": [lo, hi], "xscale", "yscale"}.
        """

        fig    = mpw.getFigure()
        xlabel = plot.get("xlabel", "")
        ylabel = plot.get("ylabel", "")
        title  = plot.get("title", "")
        xscale = float(plot.get("xscale", 1.0))
        yscale = float(plot.get("yscale", 1.0))

        fig.clear()
        ax = fig.add_subplot(111, title=title)
        ax.clear()
        self.cleanAxes(ax)
        for item in plot.get("curves", []):
            x = numpy.asarray(item["x"], dtype=float) * xscale
            y = numpy.asarray(item["y"], dtype=float) * yscale

            pen       = item.get("pen") or {}
            linestyle = '' if pen.get("style") == "none" else '-'
            color     = tuple(pen.get("color", (1.0, 1.0, 1.0, 1.0)))

            symbol          = self.SYMBOLS.get(item.get("symbol"), "")
            markeredgecolor = tuple(item.get("symbolPen", (0.0, 0.0, 0.0, 1.0)))
            markerfacecolor = tuple(item.get("symbolBrush", (0.0, 0.0, 0.0, 1.0)))
            markersize      = item.get("symbolSize", 10)

            if item.get("fillLevel") is not None and item.get("fillBrush") is not None:
                ax.fill_between(x=x, y1=y, y2=item["fillLevel"], facecolor=tuple(item["fillBrush"]))
            ax.plot(x, y, marker=symbol, color=color, linewidth=pen.get("width", 1), linestyle=linestyle, markeredgecolor=markeredgecolor, markerfacecolor=markerfacecolor, markersize=markersize)
            xr, yr = plot["xrange"], plot["yrange"]
            ax.set_xbound(xr[0] * xscale, xr[1] * xscale)
            ax.set_ybound(yr[0] * yscale, yr[1] * yscale)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        mpw.draw()
