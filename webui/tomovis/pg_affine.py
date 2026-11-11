"""Port of pyqtgraph 0.14's affineSlice and order-1 interpolateArray.

TomoVis extracts the ROI tomogram through ``LineSegmentROI.getArrayRegion``,
which calls ``pyqtgraph.functions.affineSlice`` with ``order=1`` and so
pyqtgraph's own ``interpolateArray`` rather than scipy. The methods below
repeat those numpy operations line for line (float64 weights, zero outside
the bounds, the same transposes) so the extracted samples are bit-identical.
"""

from __future__ import annotations

import numpy as np


class PgAffineSlice:
    """Arbitrary-orientation slicing of an array, as pyqtgraph.functions does it."""

    @staticmethod
    def affineSliceCoords(shape, origin, vectors, axes) -> np.ndarray:
        """Returns the sample coordinates affineSlice uses (functions.affineSliceCoords).

        Args:
            shape   : Slice shape, one length per vector.
            origin  : Coordinates of the slice origin along ``axes``.
            vectors : Direction vectors of the slice axes, each with one entry per axis.
            axes    : Data axes the vectors span.

        Returns:
            Float64 array (len(axes), *ceil(shape)) of sample coordinates.

        Raises:
            Exception : If the argument lengths disagree, as pyqtgraph raises.
        """

        if len(shape) != len(vectors):
            raise Exception("shape and vectors must have same length.")
        if len(origin) != len(axes):
            raise Exception("origin and axes must have same length.")
        for v in vectors:
            if len(v) != len(axes):
                raise Exception("each vector must be same length as axes.")

        shape = list(map(np.ceil, shape))

        if not isinstance(vectors, np.ndarray):
            vectors = np.array(vectors)
        if not isinstance(origin, np.ndarray):
            origin = np.array(origin)
        origin.shape = (len(axes),) + (1,) * len(shape)

        grid = np.mgrid[tuple([slice(0, x) for x in shape])]
        x    = (grid[np.newaxis, ...] * vectors.transpose()[(Ellipsis,) + (np.newaxis,) * len(shape)]).sum(axis=1)
        x   += origin

        return x

    @classmethod
    def affineSlice(cls, data: np.ndarray, shape, origin, vectors, axes, order: int = 1) -> np.ndarray:
        """Samples ``data`` on a regular grid of arbitrary orientation (functions.affineSlice, order 1).

        Args:
            data    : Array to sample.
            shape   : Slice shape, one length per vector.
            origin  : Coordinates of the slice origin along ``axes``.
            vectors : Direction vectors of the slice axes.
            axes    : Data axes the vectors span.
            order   : Interpolation order, 0 or 1.

        Returns:
            Sampled array with the slice axes in place of ``axes`` and the other axes kept.
        """

        x = cls.affineSliceCoords(shape, origin, vectors, axes)

        trAx = list(range(data.ndim))
        for ax in axes:
            trAx.remove(ax)
        tr1  = tuple(axes) + tuple(trAx)
        data = data.transpose(tr1)

        tr     = tuple(range(1, x.ndim)) + (0,)
        output = cls.interpolateArray(data, x.transpose(tr), order=order)

        tr  = list(range(output.ndim))
        trb = []
        for i in range(min(axes)):
            ind = tr1.index(i) + (len(shape) - len(axes))
            tr.remove(ind)
            trb.append(ind)
        tr2 = tuple(trb + tr)

        return output.transpose(tr2)

    @staticmethod
    def interpolateArray(data: np.ndarray, x: np.ndarray, default: float = 0.0, order: int = 1) -> np.ndarray:
        """Linear or nearest interpolation of ``data`` at the locations ``x`` (functions.interpolateArray).

        Args:
            data    : Array of any shape.
            x       : Locations, last axis indexing the first ``x.shape[-1]`` axes of ``data``.
            default : Value of locations outside the bounds.
            order   : 0 for nearest, 1 for linear.

        Returns:
            Array of shape ``x.shape[:-1] + data.shape[x.shape[-1]:]``.

        Raises:
            ValueError : If ``order`` is not 0 or 1.
            TypeError  : If ``x`` indexes more axes than ``data`` has.
        """

        if order not in (0, 1):
            raise ValueError("interpolateArray requires order=0 or 1 (got %s)" % order)

        nd = data.ndim
        md = x.shape[-1]
        if md > nd:
            raise TypeError("x.shape[-1] must be less than or equal to data.ndim")

        totalMask = np.ones(x.shape[:-1], dtype=bool)
        if order == 0:
            xinds = np.round(x).astype(int)
            for ax in range(md):
                mask = (xinds[..., ax] >= 0) & (xinds[..., ax] <= data.shape[ax] - 1)
                xinds[..., ax][~mask] = 0
                totalMask &= mask
            result = data[tuple([xinds[..., i] for i in range(xinds.shape[-1])])]

        else:
            fields    = np.mgrid[(slice(0, order + 1),) * md]
            xmin      = np.floor(x).astype(int)
            xmax      = xmin + 1
            indexes   = np.concatenate([xmin[np.newaxis, ...], xmax[np.newaxis, ...]])
            fieldInds = []
            for ax in range(md):
                mask = (xmin[..., ax] >= 0) & (x[..., ax] <= data.shape[ax] - 1)
                totalMask &= mask

                mask &= (xmax[..., ax] < data.shape[ax])
                axisIndex = indexes[..., ax][fields[ax]]
                axisIndex[axisIndex < 0] = 0
                axisIndex[axisIndex >= data.shape[ax]] = 0
                fieldInds.append(axisIndex)

            fieldData = data[tuple(fieldInds)]

            s  = np.empty((md,) + fieldData.shape, dtype=float)
            dx = x - xmin
            for ax in range(md):
                f1     = fields[ax].reshape(fields[ax].shape + (1,) * (dx.ndim - 1))
                sax    = f1 * dx[..., ax] + (1 - f1) * (1 - dx[..., ax])
                sax    = sax.reshape(sax.shape + (1,) * (s.ndim - 1 - sax.ndim))
                s[ax]  = sax
            s      = np.prod(s, axis=0)
            result = fieldData * s
            for i in range(md):
                result = result.sum(axis=0)

        if totalMask.ndim > 0:
            result[~totalMask] = default
        elif totalMask is False:
            result[:] = default

        return result
