"""Repository revision reporting, recorded alongside run outputs for provenance."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitState:
    """Reports the revision of the checkout this code is running from."""

    @staticmethod
    def commit() -> str:
        """Returns the short HEAD hash of the repository, annotated when unclean.

        Returns:
            The 12-character commit hash, suffixed with '(dirty working tree)'
            when uncommitted changes exist, or an 'unavailable' string when git
            cannot be run or the source is not a checkout.
        """
        repo_root = Path(__file__).resolve().parents[2]

        try:
            head = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=repo_root, capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return "unavailable (git not runnable)"

        if head.returncode != 0:
            return "unavailable (not a git checkout)"

        commit = head.stdout.strip()

        status = subprocess.run(["git", "status", "--porcelain"], cwd=repo_root, capture_output=True, text=True, timeout=5)
        if status.returncode == 0 and status.stdout.strip():
            return f"{commit} (dirty working tree)"

        return commit
