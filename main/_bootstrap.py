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
        THREAD_VARS : Environment variables capping the thread pools of the BLAS, OpenMP and numexpr backends.
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
            count : Threads each backend may use.
        """
        for key in cls.THREAD_VARS:
            os.environ[key] = str(count)

    @classmethod
    def gpus(cls, gpu_ids: list) -> None:
        """Restricts the process to several CUDA devices and caps the thread pools.

        Args:
            gpu_ids : CUDA device indices the process may see, in visibility order; positions inside an inherited CUDA_VISIBLE_DEVICES mask when one is set.

        Raises:
            ValueError : If no device index is given or an index lies outside an inherited mask.
        """
        cls._stash_inherited_mask()
        os.environ["CUDA_VISIBLE_DEVICES"] = ",".join(cls._mask_tokens(gpu_ids))
        cls.threads()

    @classmethod
    def gpu(cls, gpu_id: int, expandable_segments: bool = False) -> None:
        """Restricts the process to one CUDA device and caps the thread pools.

        Args:
            gpu_id              : CUDA device index the process may see; a position inside an inherited CUDA_VISIBLE_DEVICES mask when one is set.
            expandable_segments : Whether the torch caching allocator is allowed to grow its segments, which reduces fragmentation.

        Raises:
            ValueError : If the index lies outside an inherited mask.
        """
        cls._stash_inherited_mask()
        os.environ["CUDA_VISIBLE_DEVICES"] = cls._mask_tokens([gpu_id])[0]
        cls.threads()

        if expandable_segments:
            os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

    @classmethod
    def _stash_inherited_mask(cls) -> None:
        """Records the CUDA_VISIBLE_DEVICES this process inherited before the pin overwrites it.

        The value is exported as TOMOSAR_INHERITED_CUDA_MASK, an empty string
        standing for an unset mask, so a fan-out parent's GpuQueue can hand
        each unit the environment the parent itself received instead of the
        parent's own single-device pin. Only the first pin records; later pins
        in the same process keep the original snapshot.
        """
        if "TOMOSAR_INHERITED_CUDA_MASK" not in os.environ:
            os.environ["TOMOSAR_INHERITED_CUDA_MASK"] = os.environ.get("CUDA_VISIBLE_DEVICES", "")

    @classmethod
    def _mask_tokens(cls, gpu_ids: list) -> list:
        """Maps requested device indices to the CUDA_VISIBLE_DEVICES tokens to expose.

        A scheduler such as SLURM hands the process its GPU share through an
        already-set CUDA_VISIBLE_DEVICES; a requested index is then a position
        inside that allocation, so the token is picked from the inherited mask
        instead of naming a physical device the allocation may not hold. With
        no inherited mask the indices name physical devices directly.

        Args:
            gpu_ids : Requested CUDA device indices, in visibility order.

        Returns:
            Device tokens for CUDA_VISIBLE_DEVICES, one per requested index.

        Raises:
            ValueError : If no device index is given or an index lies outside the inherited mask.
        """
        ids = [int(gpu_id) for gpu_id in gpu_ids]
        if not ids:
            raise ValueError("gpu_ids must name at least one CUDA device")

        raw = os.environ.get("CUDA_VISIBLE_DEVICES")
        if raw is None:
            return [str(gpu_id) for gpu_id in ids]

        inherited = [token.strip() for token in raw.split(",") if token.strip()]
        outside   = [gpu_id for gpu_id in ids if gpu_id < 0 or gpu_id >= len(inherited)]
        if outside:
            raise ValueError(f"gpu index(es) {outside} lie outside the inherited CUDA_VISIBLE_DEVICES='{raw}' mask of {len(inherited)} device(s); the process may only address its allocation's share by position")

        return [inherited[gpu_id] for gpu_id in ids]
