"""Restoration of the CUDA device mask a GPU-pinned parent process inherited.

Every entry point pins itself to its devices through EnvironmentPinner, which
first exports the CUDA_VISIBLE_DEVICES it inherited as
TOMOSAR_INHERITED_CUDA_MASK (an empty string standing for unset) and then
overwrites the mask with its own pin. Any component that launches a child
meant to resolve a --gpu index against the original mask — a fan-out worker,
a DDP rank, a detached re-exec — restores that snapshot through this module
instead of forwarding the parent's pin.
"""

from __future__ import annotations

import os


class InheritedCudaMask:
    """Rebuilds a child environment carrying the parent's pre-pin CUDA mask.

    Attributes:
        STASH_VAR : Environment variable EnvironmentPinner stashes the inherited CUDA_VISIBLE_DEVICES into before pinning, an empty string standing for unset.
    """

    STASH_VAR = "TOMOSAR_INHERITED_CUDA_MASK"

    @classmethod
    def restored(cls) -> dict:
        """Returns a copy of the process environment with the inherited CUDA mask restored.

        The stash marker is dropped so the child records its own snapshot when
        it pins itself. An empty stash means the parent inherited no mask, so
        CUDA_VISIBLE_DEVICES is removed; a missing stash means the parent never
        pinned, so the environment is forwarded unchanged.

        Returns:
            The child environment with CUDA_VISIBLE_DEVICES holding the mask the parent originally saw, or absent when the parent saw none.
        """
        env     = dict(os.environ)
        stashed = env.pop(cls.STASH_VAR, None)

        if stashed == "":
            env.pop("CUDA_VISIBLE_DEVICES", None)
        elif stashed is not None:
            env["CUDA_VISIBLE_DEVICES"] = stashed

        return env
