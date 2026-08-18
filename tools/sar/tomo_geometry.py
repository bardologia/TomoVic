"""Steering vectors and outer products of a synthetic tomographic acquisition geometry."""

from __future__ import annotations

import math

import torch


class TomoGeometry:
    """Holds the kz vector and the steering basis of a simulated track stack.

    kz is either taken verbatim from the configuration or derived from the
    baselines through 4*pi*b/(lambda*r0), divided by sin(look angle) when the
    height-axis convention is vertical height.

    Attributes:
        cfg: Tomogram configuration supplying kz, baselines and geometry.
        kz: Vertical wavenumber per track in rad/m, shape (n_tracks,).
        n_tracks: Number of tracks in the geometry.
        steering: Complex steering matrix of shape (n_tracks, n_heights).
        outer: Per-height steering outer products, shape
            (n_tracks, n_tracks, n_heights).
        CONVENTIONS: Accepted height-axis conventions.
    """

    CONVENTIONS = ("height", "slant")

    def __init__(self, cfg, x_axis: torch.Tensor):
        """Derives kz and builds the steering basis over a height axis.

        Args:
            cfg: Configuration carrying kz_values, baselines, wavelength,
                slant_range, look_angle_deg and height_axis_convention.
            x_axis: Height axis samples in metres, shape (n_heights,), whose
                dtype and device the geometry tensors adopt.

        Raises:
            ValueError: If the height-axis convention is unknown or the geometry
                ends up with no tracks.
        """
        self.cfg = cfg

        if cfg.height_axis_convention not in self.CONVENTIONS:
            raise ValueError(f"Unknown height_axis_convention '{cfg.height_axis_convention}', expected one of {self.CONVENTIONS}")

        if len(cfg.kz_values) > 0:
            kz_list = [float(v) for v in cfg.kz_values]
        else:
            scale = 4.0 * math.pi / (cfg.wavelength * cfg.slant_range)

            if cfg.height_axis_convention == "height":
                scale = scale / math.sin(math.radians(cfg.look_angle_deg))

            kz_list = [scale * float(b) for b in cfg.baselines]

        self.kz       = torch.tensor(kz_list, dtype=x_axis.dtype, device=x_axis.device)
        self.n_tracks = self.kz.shape[0]

        if self.n_tracks == 0:
            raise ValueError("TomoGeometry requires at least one track: both cfg.kz_values and cfg.baselines are empty")

        phase         = self.kz.reshape(-1, 1) * x_axis.reshape(1, -1)
        self.steering = torch.polar(torch.ones_like(phase), phase)
        self.outer    = torch.einsum("ik,jk->ijk", self.steering, self.steering.conj())

    def _kz_source(self) -> str:
        """Returns a label naming how kz was obtained, for the description table."""
        if len(self.cfg.kz_values) > 0:
            return "explicit kz_values"

        if self.cfg.height_axis_convention == "height":
            return "baselines via 4*pi*b/(lambda*r0*sin(look))"

        return "baselines via 4*pi*b/(lambda*r0)"

    def describe(self) -> dict:
        """Returns a table of track count, kz range in rad/m and geometry settings for logging."""
        return {
            "Tracks"           : self.n_tracks,
            "kz min"           : f"{float(self.kz.min()):.4f} rad/m",
            "kz max"           : f"{float(self.kz.max()):.4f} rad/m",
            "Wavelength"       : f"{self.cfg.wavelength} m",
            "Slant range"      : f"{self.cfg.slant_range} m",
            "Look angle"       : f"{self.cfg.look_angle_deg} deg",
            "Axis convention"  : self.cfg.height_axis_convention,
            "kz source"        : self._kz_source(),
            "Baselines origin" : self.cfg.baselines_origin,
        }
