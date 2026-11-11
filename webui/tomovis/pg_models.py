"""State models of the pyqtgraph objects the TomoVis window touches.

The copied window calls the same methods on these models that it called on
pyqtgraph's ImageView, LineSegmentROI, InfiniteLine and ColorMap. The models
keep exactly the state those calls set (image, colour table, levels and level
mode, histogram range, ROI state and handles, which view holds which item)
and run pyqtgraph's own algorithms where TomoVis depends on them: the ROI
change detection of ``ROI.stateChanged`` with QPointF's fuzzy comparison, and
``LineSegmentROI.getArrayRegion`` through the affineSlice port. Drawing and
mouse interaction belong to the browser, which reads these models from the
window snapshot.
"""

from __future__ import annotations

import math

import numpy as np

from tomovis.pg_affine  import PgAffineSlice
from tomovis.qt_widgets import Signal, SlotBoundary


class PgPoint:
    """pyqtgraph's Point (a QPointF) with its arithmetic and QPointF's fuzzy equality.

    Attributes:
        xp : x coordinate.
        yp : y coordinate.
    """

    __slots__ = ("xp", "yp")

    def __init__(self, *args) -> None:
        """Builds a point from (x, y), a length-2 sequence, another point or one number for both coordinates.

        Args:
            args : Coordinates as Point accepts them.
        """

        if len(args) == 1 and isinstance(args[0], (int, float, np.integer, np.floating)):
            self.xp = float(args[0])
            self.yp = float(args[0])
        elif len(args) == 1:
            self.xp = float(args[0][0])
            self.yp = float(args[0][1])
        else:
            self.xp = float(args[0])
            self.yp = float(args[1])

    def x(self) -> float:
        """Returns the x coordinate."""

        return self.xp

    def y(self) -> float:
        """Returns the y coordinate."""

        return self.yp

    def __len__(self) -> int:
        """Returns 2, so numpy and zip see a length-2 sequence."""

        return 2

    def __getitem__(self, index: int) -> float:
        """Returns coordinate 0 (x) or 1 (y).

        Raises:
            IndexError : For any other index.
        """

        if index == 0:
            return self.xp
        if index == 1:
            return self.yp
        raise IndexError("Point has no index %s" % str(index))

    def __iter__(self):
        """Yields x then y."""

        yield self.xp
        yield self.yp

    def math(self, op: str, other) -> PgPoint:
        """Applies a float operator coordinate-wise, as Point._math_.

        Args:
            op    : Float dunder method name.
            other : Point, sequence or number.

        Returns:
            The resulting point.
        """

        other = other if isinstance(other, PgPoint) else PgPoint(other)
        return PgPoint(getattr(self.xp, op)(other.xp), getattr(self.yp, op)(other.yp))

    def __add__(self, other) -> PgPoint:
        """Adds coordinate-wise."""

        return self.math("__add__", other)

    def __radd__(self, other) -> PgPoint:
        """Adds coordinate-wise from the left."""

        return self.math("__radd__", other)

    def __sub__(self, other) -> PgPoint:
        """Subtracts coordinate-wise."""

        return self.math("__sub__", other)

    def __rsub__(self, other) -> PgPoint:
        """Subtracts coordinate-wise from the left."""

        return self.math("__rsub__", other)

    def __mul__(self, other) -> PgPoint:
        """Multiplies coordinate-wise."""

        return self.math("__mul__", other)

    def __rmul__(self, other) -> PgPoint:
        """Multiplies coordinate-wise from the left (tuple * Point in ROI.stateChanged)."""

        return self.math("__rmul__", other)

    def __truediv__(self, other) -> PgPoint:
        """Divides coordinate-wise."""

        return self.math("__truediv__", other)

    @staticmethod
    def fuzzyEqual(a: float, b: float) -> bool:
        """Compares two coordinates as QPointF::operator== does in Qt 5.15.

        Args:
            a : First coordinate.
            b : Second coordinate.

        Returns:
            qFuzzyIsNull(a - b) when either is zero, else qFuzzyCompare(a, b).
        """

        if a == 0.0 or b == 0.0:
            return abs(a - b) <= 0.000000000001
        return abs(a - b) * 1000000000000.0 <= min(abs(a), abs(b))

    def __eq__(self, other) -> bool:
        """Compares with QPointF's fuzzy rule."""

        other = other if isinstance(other, PgPoint) else PgPoint(other)
        return self.fuzzyEqual(self.xp, other.xp) and self.fuzzyEqual(self.yp, other.yp)

    def __ne__(self, other) -> bool:
        """Negation of __eq__."""

        return not self.__eq__(other)

    def __hash__(self) -> int:
        """Hashes the coordinates."""

        return hash((self.xp, self.yp))

    def length(self) -> float:
        """Returns the vector length (math.hypot, as Point.length)."""

        return math.hypot(self.xp, self.yp)

    def norm(self) -> PgPoint:
        """Returns the unit vector in the same direction (Point.norm)."""

        return self / self.length()

    def __repr__(self) -> str:
        """Returns the Point repr."""

        return "Point(%f, %f)" % (self.xp, self.yp)


class PgColorMap:
    """A pyqtgraph ColorMap built from a TomoVis colour table.

    Attributes:
        pos   : Stop positions in 0..1.
        color : Uint8 colours (stops, 3).
        index : Index of the colour table in TomoVisTools.colortables, sent to the browser.
    """

    def __init__(self, pos: np.ndarray, color: np.ndarray, index: int) -> None:
        """Stores the stops.

        Args:
            pos   : Stop positions, shape (256,).
            color : Stop colours, shape (256, 3) uint8.
            index : Colour table index.
        """

        self.pos   = pos
        self.color = color
        self.index = int(index)


class PgImageItemModel:
    """The ImageItem of a view; its coordinate system equals the data indices (identity transform).

    Attributes:
        view : The owning image view model.
    """

    def __init__(self, view) -> None:
        """Binds the item to its view.

        Args:
            view : Owning PgImageViewModel.
        """

        self.view = view

    def scene(self):
        """Returns the view acting as the item's scene."""

        return self.view


class PgImageViewModel:
    """What TomoVis sets on one pyqtgraph ImageView.

    Level handling follows HistogramLUTItem: in mono mode one region, in rgba
    mode one region per channel plus alpha. TomoVis passes per-channel level
    lists for its RGB views, which raise in pyqtgraph 0.14; decision D-1 routes
    them to the rgba mode as pyqtgraph's own per-channel mechanism.

    Attributes:
        name            : View attribute name ("imv1_1", "imv1_2", "imv2_1", "imv2_2").
        image           : Copy of the image last set, None when cleared.
        image_serial    : Bumped whenever the image content changes.
        apply_serial    : Bumped on every call TomoVis makes; tells the browser to re-apply LUT, range and levels.
        colortable      : Colour table index of the last setColorMap, None before any.
        level_mode      : "mono" or "rgba".
        mono_levels     : (min, max) of the mono region.
        rgba_levels     : (min, max) of the red, green, blue and alpha regions.
        histogram_range : Raw [min, max] of the last setHistogramRange, None before any.
        imageItem       : The view's image item, used as the target of getArrayRegion.
        scene           : The view itself; pyqtgraph scenes map one to one onto views here.
    """

    def __init__(self, name: str) -> None:
        """Creates an empty view in mono level mode with pyqtgraph's default region (0, 1).

        Args:
            name : View attribute name.
        """

        self.name            = name
        self.image           = None
        self.image_serial    = 0
        self.apply_serial    = 0
        self.colortable      = None
        self.level_mode      = "mono"
        self.mono_levels     = (0.0, 1.0)
        self.rgba_levels     = [(0.0, 1.0)] * 4
        self.histogram_range = None
        self.imageItem       = PgImageItemModel(self)
        self.scene           = self

    def setImage(self, img, autoRange: bool = True, autoLevels: bool = True, autoHistogramRange: bool = True) -> None:
        """Shows an image without any automatic ranging, as TomoVis always calls it.

        Args:
            img                : 2-D float image or (w, h, 3) uint8 RGB image, column-major as pyqtgraph displays it.
            autoRange          : Must be False.
            autoLevels         : Must be False.
            autoHistogramRange : Must be False.

        Raises:
            ValueError : If any automatic option is requested; TomoVis never asks for one.
        """

        if autoRange or autoLevels or autoHistogramRange:
            raise ValueError("TomoVis sets images with autoRange, autoLevels and autoHistogramRange off")

        image = np.array(img, copy=True)
        if self.image is None or self.image.shape != image.shape or self.image.dtype != image.dtype or not np.array_equal(self.image, image):
            self.image_serial += 1
        self.image         = image
        self.apply_serial += 1

    def setColorMap(self, cmap: PgColorMap) -> None:
        """Sets the colour map of the gradient editor."""

        self.colortable    = cmap.index
        self.apply_serial += 1

    def setHistogramRange(self, mn, mx) -> None:
        """Sets the histogram's value range; the browser pads it by 10 % as pyqtgraph does."""

        self.histogram_range = [float(mn), float(mx)]
        self.apply_serial   += 1

    def setLevelMode(self, mode: str) -> None:
        """Switches the level mode, carrying the old levels over as HistogramLUTItem.setLevelMode does.

        Args:
            mode : "mono" or "rgba".
        """

        if mode == self.level_mode:
            return

        old             = self.getLevels()
        self.level_mode = mode
        if mode == "mono":
            levels           = np.array(old).mean(axis=0)
            self.mono_levels = (float(levels[0]), float(levels[1]))
        else:
            self.rgba_levels = [(float(old[0]), float(old[1]))] * 4

    def channels(self) -> int:
        """Returns the image's channel count as ImageItem.channels, 3 when there is no image."""

        if self.image is None or self.image.ndim == 2:
            return 3 if self.image is None else 1
        return int(self.image.shape[2])

    def getLevels(self):
        """Returns the levels as HistogramLUTItem.getLevels: one pair in mono mode, one per channel in rgba mode."""

        if self.level_mode == "mono":
            return self.mono_levels
        return self.rgba_levels[:self.channels()]

    def setLevels(self, mn, mx) -> None:
        """Sets the levels.

        Scalars set the mono region (or every rgba region while in rgba mode).
        Lists are TomoVis's per-channel RGB call (E-001, E-002): rgba mode with
        one (min, max) pair per list entry (D-1).

        Args:
            mn : Lower level, or one lower level per channel.
            mx : Upper level, or one upper level per channel.
        """

        if isinstance(mn, list):
            self.setLevelMode("rgba")
            pairs = [(float(low), float(high)) for low, high in zip(mn, mx)]
            for index, pair in enumerate(pairs[:4]):
                self.rgba_levels[index] = pair
        elif self.level_mode == "mono":
            self.mono_levels = (float(mn), float(mx))
        else:
            self.rgba_levels = [(float(mn), float(mx))] * 4
        self.apply_serial += 1

    def clear(self) -> None:
        """Removes the image."""

        if self.image is not None:
            self.image_serial += 1
        self.image         = None
        self.apply_serial += 1

    def addItem(self, item) -> None:
        """Adds a graphics item, moving it out of the view that held it."""

        item.view = self

    def removeItem(self, item) -> None:
        """Removes a graphics item when this view holds it.

        pyqtgraph detaches an item held by another view from that view's
        coordinate group; TomoVis follows every such call with a removal or an
        addItem on the holding view, so the end state equals this model's.
        """

        if item.view is self:
            item.view = None

    def snapshot(self) -> dict:
        """Returns the view state the browser applies.

        Returns:
            has_image, image shape and dtype, both serials, colour table, level mode, levels and raw histogram range.
        """

        levels = self.getLevels()
        return {
            "has_image"       : self.image is not None,
            "image_shape"     : list(self.image.shape) if self.image is not None else None,
            "image_dtype"     : str(self.image.dtype) if self.image is not None else None,
            "image_serial"    : self.image_serial,
            "apply_serial"    : self.apply_serial,
            "colortable"      : self.colortable,
            "level_mode"      : self.level_mode,
            "levels"          : [float(levels[0]), float(levels[1])] if self.level_mode == "mono" else [[float(low), float(high)] for low, high in levels],
            "histogram_range" : self.histogram_range,
        }


class PgHandleModel:
    """A free ROI handle: only its position in ROI coordinates.

    Attributes:
        position : Handle position in ROI-local coordinates.
    """

    def __init__(self) -> None:
        """Places the handle at the origin."""

        self.position = PgPoint(0.0, 0.0)

    def pos(self) -> PgPoint:
        """Returns a copy of the position."""

        return PgPoint(self.position)

    def setPos(self, *args) -> None:
        """Moves the handle; accepts (x, y) or one point."""

        self.position = PgPoint(*args)


class PgLineSegmentRoiModel:
    """pyqtgraph's LineSegmentROI: origin, size, angle and two free handles.

    Attributes:
        boundary         : Slot boundary for sigRegionChanged.
        pen_args         : Pen keyword arguments TomoVis passed, kept for reference; the browser draws the line.
        state            : {"pos", "size", "angle"} as ROI.state.
        handles          : Handle infos {"name", "type", "pos", "item"} as ROI.handles.
        lastState        : State at the end of the previous stateChanged.
        freeHandleMoved  : Whether a free handle moved since the last change signal.
        sigRegionChanged : Signal(object) emitted by stateChanged when the region changed.
        view             : Image view model holding the ROI, None when in no view.
        serial           : Bumped when server code moves the ROI (Set, session restore), so the browser re-reads its geometry.
        blocked          : Signal blocking flag (never set by TomoVis).
    """

    def __init__(self, positions, boundary: SlotBoundary, pos=None, **pen_args) -> None:
        """Creates the ROI as LineSegmentROI.__init__ does, before any slot is connected.

        Args:
            positions : Two endpoints in ROI coordinates.
            boundary  : Slot boundary for the change signal.
            pos       : ROI origin, (0, 0) when None.
            pen_args  : Pen, hover pen, handle pens, translateSnap and removable as passed by TomoVis.
        """

        self.boundary         = boundary
        self.pen_args         = pen_args
        self.state            = {"pos": PgPoint(pos if pos is not None else [0, 0]), "size": PgPoint(1, 1), "angle": 0.0}
        self.handles          = []
        self.freeHandleMoved  = False
        self.sigRegionChanged = Signal(self, "sigRegionChanged")
        self.view             = None
        self.serial           = 0
        self.blocked          = False

        for position in positions:
            handle = PgHandleModel()
            info   = {"name": None, "type": "f", "pos": PgPoint(position), "item": handle}
            handle.setPos(info["pos"] * self.state["size"])
            self.handles.append(info)

        self.lastState = self.getState()

    def signalsBlocked(self) -> bool:
        """Returns whether the ROI's signals are blocked."""

        return self.blocked

    def scene(self):
        """Returns the view holding the ROI."""

        return self.view

    def getHandles(self) -> list[PgHandleModel]:
        """Returns the handle items."""

        return [handle["item"] for handle in self.handles]

    @property
    def endpoints(self) -> list[PgHandleModel]:
        """The two handle items, as LineSegmentROI.endpoints."""

        return self.getHandles()

    def getState(self) -> dict:
        """Returns copies of pos, size, angle and the handle positions (LineSegmentROI.getState)."""

        return {
            "pos"    : PgPoint(self.state["pos"]),
            "size"   : PgPoint(self.state["size"]),
            "angle"  : self.state["angle"],
            "points" : [PgPoint(handle.pos()) for handle in self.getHandles()],
        }

    def setPos(self, pos, y=None, update: bool = True, finish: bool = True) -> None:
        """Moves the origin (ROI.setPos).

        Args:
            pos    : New origin, or its x coordinate when ``y`` is given.
            y      : y coordinate, None when ``pos`` holds both.
            update : Whether to run stateChanged now.
            finish : Passed to stateChanged.

        Raises:
            TypeError : For a non-bool update or a bool y, as pyqtgraph raises.
        """

        if update not in (True, False):
            raise TypeError("update argument must be bool")

        if y is None:
            pos = PgPoint(pos)
        else:
            if isinstance(y, bool):
                raise TypeError("Positional arguments to setPos() must be numerical.")
            pos = PgPoint(pos, y)

        self.state["pos"] = pos
        if update:
            self.stateChanged(finish=finish)

    def stateChanged(self, finish: bool = True) -> None:
        """Processes a state change as ROI.stateChanged.

        When pos, size, angle or a handle position differs from lastState
        (QPointF fuzzy comparison) the handles are re-placed and
        sigRegionChanged is emitted; otherwise it is emitted only when a free
        handle moved.

        Args:
            finish : Whether the change is final; the finish signal has no TomoVis connection.
        """

        changed = False
        if self.lastState is None:
            changed = True
        else:
            state = self.getState()
            for key in list(state.keys()):
                if state[key] != self.lastState[key]:
                    changed = True

        if changed:
            for handle in self.handles:
                handle["item"].setPos(handle["pos"] * self.state["size"])
            self.sigRegionChanged.emit(self)
        elif self.freeHandleMoved:
            self.sigRegionChanged.emit(self)

        self.freeHandleMoved = False
        self.lastState       = self.getState()

    def applyClientState(self, state: dict, freeHandleMoved: bool) -> None:
        """Stores the state a browser drag produced, before the caller runs stateChanged.

        Args:
            state           : {"pos": [x, y], "size": [w, h], "angle": deg, "handles": [{"pos": [x, y], "item": [x, y]}, ...]}.
            freeHandleMoved : Whether the drag moved a free handle.
        """

        self.state["pos"]   = PgPoint(state["pos"])
        self.state["size"]  = PgPoint(state["size"])
        self.state["angle"] = float(state["angle"])
        for info, handle in zip(self.handles, state["handles"]):
            info["pos"] = PgPoint(handle["pos"])
            info["item"].setPos(PgPoint(handle["item"]))
        self.freeHandleMoved = self.freeHandleMoved or bool(freeHandleMoved)

    def rotationMap(self, point: PgPoint) -> PgPoint:
        """Maps a local point through the ROI's rotation (QTransform.rotate with Qt's exact quarter turns).

        Args:
            point : Point in ROI-local coordinates.

        Returns:
            The rotated point.
        """

        degrees = self.state["angle"] % 360.0
        if degrees == 0.0:
            sine, cosine = 0.0, 1.0
        elif degrees == 90.0:
            sine, cosine = 1.0, 0.0
        elif degrees == 180.0:
            sine, cosine = 0.0, -1.0
        elif degrees == 270.0:
            sine, cosine = -1.0, 0.0
        else:
            radians      = math.radians(degrees)
            sine, cosine = math.sin(radians), math.cos(radians)
        return PgPoint(cosine * point.x() - sine * point.y(), sine * point.x() + cosine * point.y())

    def mapToItem(self, item: PgImageItemModel, point: PgPoint) -> PgPoint:
        """Maps a local point to the image item's coordinates (rotation, then the origin offset; the item is the identity).

        Args:
            item  : Target image item.
            point : Point in ROI-local coordinates.

        Returns:
            The point in image (data index) coordinates.
        """

        return self.rotationMap(point) + self.state["pos"]

    def getArrayRegion(self, data: np.ndarray, img: PgImageItemModel, axes=(0, 1), order: int = 1) -> np.ndarray:
        """Samples ``data`` along the line (LineSegmentROI.getArrayRegion).

        ``int(length)`` samples at unit spacing from the first endpoint,
        bilinear over ``axes``, zero outside the data. A zero-length line has
        no direction; pyqtgraph raises ZeroDivisionError in Point.norm there,
        the port samples nothing instead (crash fix E-012), which TomoVis then
        treats like any line shorter than one sample.

        Args:
            data  : Array to sample.
            img   : Image item whose coordinates the handles are mapped into.
            axes  : Data axes spanned by the image.
            order : Interpolation order.

        Returns:
            Array with ``axes`` replaced by one axis of ``int(length)`` samples.
        """

        imgPts = [self.mapToItem(img, handle.pos()) for handle in self.endpoints]

        d      = PgPoint(imgPts[1] - imgPts[0])
        o      = PgPoint(imgPts[0])
        length = d.length()
        vector = d.norm() if length > 0.0 else PgPoint(0.0, 0.0)

        return PgAffineSlice.affineSlice(data, shape=(int(length),), vectors=[vector], origin=o, axes=axes, order=order)

    def snapshot(self) -> dict:
        """Returns the ROI geometry the browser draws.

        Returns:
            view name, pos, size, angle, handles with their info and item positions, and the serial.
        """

        return {
            "view"    : self.view.name if self.view is not None else None,
            "pos"     : [self.state["pos"].x(), self.state["pos"].y()],
            "size"    : [self.state["size"].x(), self.state["size"].y()],
            "angle"   : float(self.state["angle"]),
            "handles" : [{"pos": [float(info["pos"][0]), float(info["pos"][1])], "item": [info["item"].position.x(), info["item"].position.y()]} for info in self.handles],
            "serial"  : self.serial,
        }


class PgInfiniteLineModel:
    """pyqtgraph's InfiniteLine as TomoVis uses it: a horizontal slice indicator.

    Attributes:
        position : Line value (y of the horizontal line).
        angle    : Line angle in degrees (0, horizontal).
        visible  : Whether the line is shown.
        view     : Image view model holding the line, None when in no view.
    """

    def __init__(self, pos: float = 0, angle: float = 0) -> None:
        """Creates a visible line at ``pos`` in no view.

        Args:
            pos   : Initial value.
            angle : Line angle in degrees.
        """

        self.position = pos
        self.angle    = angle
        self.visible  = True
        self.view     = None

    def setPos(self, pos) -> None:
        """Moves the line."""

        self.position = pos

    def value(self):
        """Returns the line value."""

        return self.position

    def show(self) -> None:
        """Shows the line."""

        self.visible = True

    def hide(self) -> None:
        """Hides the line."""

        self.visible = False

    def isVisible(self) -> bool:
        """Returns whether the line is shown."""

        return self.visible

    def scene(self):
        """Returns the view holding the line."""

        return self.view

    def snapshot(self) -> dict:
        """Returns view name, value and visibility for the browser."""

        return {"view": self.view.name if self.view is not None else None, "value": float(self.position), "visible": self.visible}
