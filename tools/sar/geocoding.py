"""Geocoding of radar (azimuth, slant-range) pixels to WGS84 longitude, latitude and ECEF.

The scene model turns pixel indices into a local east-north plane using the track
heading, squint and platform altitude, then fits a rigid rotation and shift of that
plane onto the surveyed scene corners stored in the track parameters.
"""

from __future__ import annotations

import math

import numpy as np

from tools.sar.track_parameters import TrackParameters


class Wgs84:
    """WGS84 ellipsoid constants and conversions between geodetic, ECEF and local ENU frames.

    Attributes:
        SEMI_MAJOR_M: Equatorial radius in metres.
        FLATTENING: Ellipsoid flattening.
        SEMI_MINOR_M: Polar radius in metres.
        ECCENTRICITY_SQ: First eccentricity squared.
        SECOND_ECC_SQ: Second eccentricity squared.
    """

    SEMI_MAJOR_M    = 6378137.0
    FLATTENING      = 1.0 / 298.257223563
    SEMI_MINOR_M    = SEMI_MAJOR_M * (1.0 - FLATTENING)
    ECCENTRICITY_SQ = FLATTENING * (2.0 - FLATTENING)
    SECOND_ECC_SQ   = ECCENTRICITY_SQ / (1.0 - ECCENTRICITY_SQ)

    @classmethod
    def geodetic_to_ecef(cls, lon_deg, lat_deg, height_m):
        """Converts geodetic coordinates to earth-centred earth-fixed cartesian coordinates.

        Args:
            lon_deg: Longitude in degrees, scalar or array.
            lat_deg: Latitude in degrees, broadcastable against lon_deg.
            height_m: Ellipsoidal height in metres, broadcastable against lon_deg.

        Returns:
            Tuple of x, y, z ECEF coordinates in metres, each with the broadcast shape.
        """
        lon = np.radians(np.asarray(lon_deg, dtype=np.float64))
        lat = np.radians(np.asarray(lat_deg, dtype=np.float64))
        h   = np.asarray(height_m, dtype=np.float64)

        sin_lat = np.sin(lat)
        cos_lat = np.cos(lat)
        prime   = cls.SEMI_MAJOR_M / np.sqrt(1.0 - cls.ECCENTRICITY_SQ * sin_lat * sin_lat)

        x = (prime + h) * cos_lat * np.cos(lon)
        y = (prime + h) * cos_lat * np.sin(lon)
        z = (prime * (1.0 - cls.ECCENTRICITY_SQ) + h) * sin_lat
        return x, y, z

    @classmethod
    def ecef_to_geodetic(cls, x, y, z):
        """Converts ECEF cartesian coordinates to geodetic coordinates via the Bowring approximation.

        Args:
            x: ECEF x in metres, scalar or array.
            y: ECEF y in metres, broadcastable against x.
            z: ECEF z in metres, broadcastable against x.

        Returns:
            Tuple of longitude in degrees, latitude in degrees, and ellipsoidal
            height in metres.
        """
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        z = np.asarray(z, dtype=np.float64)

        radial = np.hypot(x, y)
        theta  = np.arctan2(z * cls.SEMI_MAJOR_M, radial * cls.SEMI_MINOR_M)

        lat = np.arctan2(
            z + cls.SECOND_ECC_SQ * cls.SEMI_MINOR_M * np.sin(theta) ** 3,
            radial - cls.ECCENTRICITY_SQ * cls.SEMI_MAJOR_M * np.cos(theta) ** 3,
        )
        lon = np.arctan2(y, x)

        sin_lat = np.sin(lat)
        prime   = cls.SEMI_MAJOR_M / np.sqrt(1.0 - cls.ECCENTRICITY_SQ * sin_lat * sin_lat)
        height  = radial / np.cos(lat) - prime

        return np.degrees(lon), np.degrees(lat), height

    @classmethod
    def enu_axes(cls, lon_deg, lat_deg):
        """Returns the east, north and up unit vectors of the local ENU frame at a point.

        Args:
            lon_deg: Longitude of the frame origin in degrees.
            lat_deg: Latitude of the frame origin in degrees.

        Returns:
            Tuple of three unit vectors of shape (3,) expressed in ECEF axes.
        """
        lon = math.radians(lon_deg)
        lat = math.radians(lat_deg)

        east  = np.array([-math.sin(lon), math.cos(lon), 0.0])
        north = np.array([-math.sin(lat) * math.cos(lon), -math.sin(lat) * math.sin(lon), math.cos(lat)])
        up    = np.array([math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)])
        return east, north, up


class SceneGeocoder:
    """Maps radar pixel coordinates of a scene to WGS84 longitude, latitude and ECEF.

    The forward model places a pixel on a local east-north plane from the slant
    range, azimuth spacing, squint and platform height, then applies the rigid
    2-D rotation and translation fitted to the surveyed scene corners.

    Attributes:
        ps_az: Azimuth pixel spacing in metres.
        ps_rg: Slant-range pixel spacing in metres.
        h0: Platform altitude in metres.
        heading_rad: Track heading in radians clockwise from north.
        squint_rad: Antenna squint angle in radians.
        r0: Slant range of the first range sample in metres.
        corner_rg: Range pixel index of each surveyed corner.
        corner_az: Azimuth pixel index of each surveyed corner.
        corner_lon: Longitude of each surveyed corner in degrees.
        corner_lat: Latitude of each surveyed corner in degrees.
        corner_h: Height of each surveyed corner in metres.
        anchor_lon: Longitude in degrees of the local ENU frame origin.
        anchor_lat: Latitude in degrees of the local ENU frame origin.
        origin_ecef: ECEF position of the ENU frame origin, shape (3,).
        east_axis: ENU east unit vector in ECEF axes, shape (3,).
        north_axis: ENU north unit vector in ECEF axes, shape (3,).
        up_axis: ENU up unit vector in ECEF axes, shape (3,).
        rot_cos: Cosine of the fitted plane rotation.
        rot_sin: Sine of the fitted plane rotation.
        shift: Fitted east-north translation in metres, shape (2,).
        corner_residuals_m: Per-corner fit residual in metres, shape (n_corners,).
        REQUIRED_KEYS: Reference-track parameter keys the model needs.
    """

    REQUIRED_KEYS = ("ps_az", "ps_rg", "h0", "heading", "squint", "antdir", "r", "geo_poly")

    def __init__(self, reference: dict) -> None:
        """Validates the reference track parameters and fits the scene anchor.

        Args:
            reference: Parameter dictionary of the reference track, holding at
                least the keys in REQUIRED_KEYS.

        Raises:
            KeyError: If any required parameter key is absent.
            ValueError: If the geometry is left-looking, the slant-range axis is
                not uniform with spacing ps_rg, or fewer than three matched
                corners are available in geo_poly.
        """
        missing = [key for key in self.REQUIRED_KEYS if key not in reference]
        if missing:
            raise KeyError(f"reference track parameters lack {missing}; the scene cannot be geocoded")

        if reference["antdir"] <= 0:
            raise ValueError("the geocoding model assumes a right-looking geometry (antdir > 0)")

        self.ps_az       = float(reference["ps_az"])
        self.ps_rg       = float(reference["ps_rg"])
        self.h0          = float(reference["h0"])
        self.heading_rad = math.radians(float(reference["heading"]))
        self.squint_rad  = math.radians(float(reference["squint"]))

        slant   = np.asarray(reference["r"], dtype=np.float64)
        self.r0 = float(slant[0])

        drift = abs(self.r0 + (slant.size - 1) * self.ps_rg - float(slant[-1]))
        if drift > 0.5 * self.ps_rg:
            raise ValueError(f"slant-range axis is not uniform with spacing ps_rg={self.ps_rg}: end drift {drift:.3f} m")

        poly   = reference["geo_poly"]
        pixels = np.asarray(poly["pixels"], dtype=np.float64).reshape(-1, 2)
        lonlat = np.asarray(poly["lonlat"], dtype=np.float64).reshape(-1, 3)

        if pixels.shape[0] != lonlat.shape[0] or pixels.shape[0] < 3:
            raise ValueError(f"geo_poly needs at least 3 matched corners: got {pixels.shape[0]} pixel pairs and {lonlat.shape[0]} lonlat triples")

        self.corner_rg  = pixels[:, 0]
        self.corner_az  = pixels[:, 1]
        self.corner_lon = lonlat[:, 0]
        self.corner_lat = lonlat[:, 1]
        self.corner_h   = lonlat[:, 2]

        self._fit_anchor()

    @classmethod
    def from_track_parameters(cls, params: TrackParameters) -> "SceneGeocoder":
        """Returns a geocoder built from the reference track of a parameter collection."""
        return cls(params.parameters[0])

    @property
    def residual_rms_m(self) -> float:
        """Root-mean-square corner fit residual in metres."""
        return float(np.sqrt(np.mean(self.corner_residuals_m ** 2)))

    @property
    def residual_max_m(self) -> float:
        """Largest corner fit residual in metres."""
        return float(np.max(self.corner_residuals_m))

    def _model_plane(self, az_px, rg_px, height_m):
        """Returns unaligned east-north coordinates of radar pixels from the acquisition geometry.

        Args:
            az_px: Azimuth pixel indices, scalar or array.
            rg_px: Range pixel indices, broadcastable against az_px.
            height_m: Target height in metres, broadcastable against az_px.

        Returns:
            Tuple of east and north offsets in metres before the rigid alignment.

        Raises:
            ValueError: If the slant range is shorter than the platform height
                drop, so the ground range would be imaginary.
        """
        slant = self.r0 + np.asarray(rg_px, dtype=np.float64) * self.ps_rg
        along = np.asarray(az_px, dtype=np.float64) * self.ps_az + slant * math.sin(self.squint_rad)
        drop  = self.h0 - np.asarray(height_m, dtype=np.float64)

        if np.any(slant <= np.abs(drop)):
            raise ValueError("slant range shorter than the platform height drop; heights and track altitude are inconsistent")

        ground   = np.sqrt(slant * slant - drop * drop)
        head_e   = math.sin(self.heading_rad)
        head_n   = math.cos(self.heading_rad)

        east  = along * head_e + ground * head_n
        north = along * head_n - ground * head_e
        return east, north

    def _observed_enu(self):
        """Returns the surveyed corners as east-north offsets of shape (n_corners, 2) in metres."""
        x, y, z = Wgs84.geodetic_to_ecef(self.corner_lon, self.corner_lat, np.zeros_like(self.corner_lon))
        delta   = np.stack([x, y, z], axis=1) - np.asarray(self.origin_ecef)

        return np.stack([delta @ self.east_axis, delta @ self.north_axis], axis=1)

    def _fit_anchor(self) -> None:
        """Fits the ENU frame origin and the rigid rotation and shift onto the surveyed corners."""
        self.anchor_lon = float(np.mean(self.corner_lon))
        self.anchor_lat = float(np.mean(self.corner_lat))

        origin           = Wgs84.geodetic_to_ecef(self.anchor_lon, self.anchor_lat, 0.0)
        self.origin_ecef = np.array([float(origin[0]), float(origin[1]), float(origin[2])])

        self.east_axis, self.north_axis, self.up_axis = Wgs84.enu_axes(self.anchor_lon, self.anchor_lat)

        model_e, model_n = self._model_plane(self.corner_az, self.corner_rg, self.corner_h)
        model            = np.stack([model_e, model_n], axis=1)
        observed         = self._observed_enu()

        model_center    = model.mean(axis=0)
        observed_center = observed.mean(axis=0)
        model_c         = model - model_center
        observed_c      = observed - observed_center

        angle    = math.atan2(
            float(np.sum(model_c[:, 0] * observed_c[:, 1] - model_c[:, 1] * observed_c[:, 0])),
            float(np.sum(model_c[:, 0] * observed_c[:, 0] + model_c[:, 1] * observed_c[:, 1])),
        )
        self.rot_cos = math.cos(angle)
        self.rot_sin = math.sin(angle)

        rotated_center = np.array([
            self.rot_cos * model_center[0] - self.rot_sin * model_center[1],
            self.rot_sin * model_center[0] + self.rot_cos * model_center[1],
        ])
        self.shift = observed_center - rotated_center

        aligned = np.stack([
            self.rot_cos * model[:, 0] - self.rot_sin * model[:, 1] + self.shift[0],
            self.rot_sin * model[:, 0] + self.rot_cos * model[:, 1] + self.shift[1],
        ], axis=1)
        self.corner_residuals_m = np.linalg.norm(aligned - observed, axis=1)

    def _aligned_enu(self, az_px, rg_px, height_m):
        """Returns east and north offsets in metres after applying the fitted rotation and shift."""
        raw_e, raw_n = self._model_plane(az_px, rg_px, height_m)

        east  = self.rot_cos * raw_e - self.rot_sin * raw_n + self.shift[0]
        north = self.rot_sin * raw_e + self.rot_cos * raw_n + self.shift[1]
        return east, north

    def geocode(self, az_px, rg_px, height_m):
        """Geocodes radar pixels at a given height to longitude, latitude and ECEF positions.

        Args:
            az_px: Azimuth pixel indices of shape (n,).
            rg_px: Range pixel indices of shape (n,).
            height_m: Target heights in metres, broadcastable to shape (n,).

        Returns:
            Tuple of longitude in degrees of shape (n,), latitude in degrees of
            shape (n,), and ECEF positions in metres of shape (n, 3).
        """
        height       = np.asarray(height_m, dtype=np.float64)
        east, north  = self._aligned_enu(az_px, rg_px, height)

        return self._enu_to_geodetic(east, north, height)

    def geocode_track(self, az_px, height_m):
        """Geocodes flight-track positions along azimuth at a given altitude.

        The zero-range line of the scene model is followed, so the result traces
        the platform path rather than a ground target.

        Args:
            az_px: Azimuth pixel indices of shape (n,).
            height_m: Platform heights in metres, broadcastable to shape (n,).

        Returns:
            Tuple of longitude in degrees of shape (n,), latitude in degrees of
            shape (n,), and ECEF positions in metres of shape (n, 3).
        """
        height = np.asarray(height_m, dtype=np.float64)
        along  = np.asarray(az_px, dtype=np.float64) * self.ps_az
        raw_e  = along * math.sin(self.heading_rad)
        raw_n  = along * math.cos(self.heading_rad)

        east   = self.rot_cos * raw_e - self.rot_sin * raw_n + self.shift[0]
        north  = self.rot_sin * raw_e + self.rot_cos * raw_n + self.shift[1]

        return self._enu_to_geodetic(east, north, height)

    def _enu_to_geodetic(self, east, north, height):
        """Returns longitude, latitude and ECEF positions for east-north offsets at a height.

        Args:
            east: East offsets from the anchor in metres, shape (n,).
            north: North offsets from the anchor in metres, shape (n,).
            height: Ellipsoidal heights in metres, broadcastable to shape (n,).

        Returns:
            Tuple of longitude in degrees, latitude in degrees, and ECEF
            positions in metres of shape (n, 3).
        """
        ground        = self.origin_ecef[None, :] + np.outer(east, self.east_axis) + np.outer(north, self.north_axis)
        lon, lat, _   = Wgs84.ecef_to_geodetic(ground[:, 0], ground[:, 1], ground[:, 2])
        x, y, z       = Wgs84.geodetic_to_ecef(lon, lat, np.broadcast_to(height, lon.shape))

        return lon, lat, np.stack([x, y, z], axis=1)
