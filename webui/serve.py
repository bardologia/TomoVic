"""Command-line entry point that starts the TomoVic control console."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web_ui_server import WebUIServer


class ServeEntry:
    """Parses the console command line and starts the web UI server.

    Attributes:
        parser: Argument parser holding the host, port and project-root options.
    """

    def __init__(self) -> None:
        """Builds the argument parser with the host, port and root options."""
        self.parser = argparse.ArgumentParser(description="TomoVic control console")
        self.parser.add_argument("--host", default="127.0.0.1")
        self.parser.add_argument("--port", type=int, default=8765)
        self.parser.add_argument("--root", type=Path, default=None, help="project root the console operates on (jobs, logs, runs); defaults to the repository holding this file")

    def run(self) -> None:
        """Parses the command line and serves the console until it is stopped."""
        args   = self.parser.parse_args()
        server = WebUIServer(host=args.host, port=args.port, root=args.root)
        server.serve()


if __name__ == "__main__":
    ServeEntry().run()
