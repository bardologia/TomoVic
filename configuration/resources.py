"""Resource monitoring settings shared by training and the long-running processing entries.

Kept outside the training package so that a processing entry can carry these
settings without importing the training configurations and, through them, torch.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ResourceConfig:
    """Resource monitoring cadence and the utilisation levels that raise a warning.

    Attributes:
        enabled            : Whether the resource monitor runs alongside training.
        poll_interval_sec  : Seconds between resource samples.
        log_to_tensorboard : Whether samples are also written as TensorBoard scalars.
        warn_ram_pct       : Host RAM utilisation percentage that triggers a warning.
        warn_vram_pct      : Device VRAM utilisation percentage that triggers a warning.
        warn_shm_pct       : Shared-memory utilisation percentage that triggers a warning.
        warn_cooldown_sec  : Seconds silenced after a warning before it may repeat.
    """

    enabled            : bool  = True
    poll_interval_sec  : float = 5.0
    log_to_tensorboard : bool  = True
    warn_ram_pct       : float = 90.0
    warn_vram_pct      : float = 90.0
    warn_shm_pct       : float = 80.0
    warn_cooldown_sec  : float = 30.0
