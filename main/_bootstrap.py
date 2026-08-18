"""Entry-point bootstrap: puts the repository on `sys.path` and pins the environment.

Imported first by every script under `main/`, before any project module, so the
repository root is importable and thread and CUDA device variables are set before
torch and numpy read them.
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message=".*pynvml.*", category=FutureWarning)

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class EnvironmentPinner:
    """Sets the thread and CUDA environment variables before the numeric stack loads.

    Attributes:
        THREAD_VARS: Environment variables capping the thread pools of the BLAS,
            OpenMP and numexpr backends.
    """

    THREAD_VARS = (
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    )

    @classmethod
    def threads(cls, count: int = 4) -> None:
        """Caps every numeric backend to the same thread count.

        Args:
            count: Threads each backend may use.
        """
        for key in cls.THREAD_VARS:
            os.environ[key] = str(count)

    @classmethod
    def gpus(cls, gpu_ids: list) -> None:
        """Restricts the process to several CUDA devices and caps the thread pools.

        Args:
            gpu_ids: CUDA device indices the process may see, in visibility order.

        Raises:
            ValueError: If no device index is given.
        """
        ids = [str(int(gpu_id)) for gpu_id in gpu_ids]
        if not ids:
            raise ValueError("gpu_ids must name at least one CUDA device")

        os.environ["CUDA_VISIBLE_DEVICES"] = ",".join(ids)
        cls.threads()

    @classmethod
    def gpu(cls, gpu_id: int, expandable_segments: bool = False) -> None:
        """Restricts the process to one CUDA device and caps the thread pools.

        Args:
            gpu_id: CUDA device index the process may see.
            expandable_segments: Whether the torch caching allocator is allowed
                to grow its segments, which reduces fragmentation.
        """
        os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
        cls.threads()

        if expandable_segments:
            os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
