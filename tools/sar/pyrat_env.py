"""Process environment preparation required before importing PyRat."""

from __future__ import annotations

import os
import sys
from pathlib import Path


class PyRatEnvironment:
    """Prepares library, module and Qt settings so PyRat imports headlessly."""

    @staticmethod
    def ensure_conda_lib_on_ld_path() -> None:
        """Prepends the active conda environment's lib directory to LD_LIBRARY_PATH."""
        conda_lib = os.path.join(sys.prefix, "lib")
        ld_path   = os.environ.get("LD_LIBRARY_PATH", "")

        if conda_lib not in ld_path.split(":"):
            os.environ["LD_LIBRARY_PATH"] = conda_lib + (":" + ld_path if ld_path else "")

    @staticmethod
    def ensure_root_on_sys_path(pyrat_root: str) -> None:
        """Inserts the PyRat source root at the front of sys.path if absent."""
        if pyrat_root not in sys.path:
            sys.path.insert(0, pyrat_root)

    @staticmethod
    def ensure(pyrat_root: str | Path) -> None:
        """Applies the offscreen Qt platform, the conda library path and the PyRat import root.

        Args:
            pyrat_root: Directory holding the importable PyRat package.
        """
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        PyRatEnvironment.ensure_conda_lib_on_ld_path()
        PyRatEnvironment.ensure_root_on_sys_path(str(pyrat_root))
