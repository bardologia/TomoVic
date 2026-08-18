"""Seeding and RNG state handling that make runs reproducible.

Seeds the Python, NumPy and torch generators, forces deterministic cuDNN,
captures and restores RNG snapshots, and gives each DataLoader worker a distinct
seed that also reaches the dataset augmenters.
"""

from __future__ import annotations

import random

import numpy as np
import torch


class Reproducibility:
    """Seeds the process-wide random generators and pins deterministic kernels.

    Attributes:
        SEED_MODULUS: Modulus applied to seeds for generators bounded to 32 bits.
    """

    SEED_MODULUS = 2 ** 32

    @staticmethod
    def seed_everything(seed: int) -> None:
        """Seeds Python, NumPy and torch, and switches cuDNN to deterministic mode.

        Args:
            seed: Base seed applied to every generator.
        """
        seed = int(seed)

        random.seed(seed)
        np.random.seed(seed % Reproducibility.SEED_MODULUS)
        torch.manual_seed(seed)

        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)

        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark     = False

    @staticmethod
    def generator(seed: int) -> torch.Generator:
        """Returns a CPU torch generator seeded with the given value."""
        generator = torch.Generator()
        generator.manual_seed(int(seed))

        return generator

    @staticmethod
    def worker_init(base_seed: int):
        """Returns the DataLoader worker_init_fn deriving per-worker seeds from base_seed."""
        return WorkerInitializer(base_seed)


class RngSnapshot:
    """Captured Python, NumPy, torch and CUDA generator states.

    Attributes:
        python: State of the standard library generator.
        numpy: State of the NumPy global generator.
        torch: State of the CPU torch generator.
        cuda: Per-device CUDA generator states, empty when CUDA is unavailable.
    """

    def __init__(self) -> None:
        """Captures the current state of every random generator."""
        self.python = random.getstate()
        self.numpy  = np.random.get_state()
        self.torch  = torch.get_rng_state()
        self.cuda   = torch.cuda.get_rng_state_all() if torch.cuda.is_available() else []

    def restore(self) -> None:
        """Restores every generator to the captured state."""
        random.setstate(self.python)
        np.random.set_state(self.numpy)
        torch.set_rng_state(self.torch)

        if torch.cuda.is_available():
            torch.cuda.set_rng_state_all(self.cuda)


class WorkerInitializer:
    """Seeds a DataLoader worker and every augmenter of the dataset it holds.

    Attributes:
        base_seed: Seed the per-worker seeds are offset from.
    """

    def __init__(self, base_seed: int) -> None:
        """Initializes the callable with the base seed shared by all workers."""
        self.base_seed = int(base_seed)

    def __call__(self, worker_id: int) -> None:
        """Seeds this worker's generators and reseeds its dataset augmenters.

        Args:
            worker_id: Index of the DataLoader worker, offset from the base seed.
        """
        seed = (self.base_seed + int(worker_id)) % Reproducibility.SEED_MODULUS

        random.seed(seed)
        np.random.seed(seed)

        info = torch.utils.data.get_worker_info()
        if info is None:
            return

        for augmenter in self._augmenters(info.dataset):
            augmenter.reseed(seed)

    @staticmethod
    def _augmenters(dataset) -> list:
        """Returns the augmenters of a dataset, descending into its parts when present."""
        parts = getattr(dataset, "parts", None) or [dataset]

        return [part.augmenter for part in parts if getattr(part, "augmenter", None) is not None]
