"""Command-line entry point that starts the TomoVic control console."""

from __future__ import annotations

import argparse
import faulthandler
import ipaddress
import os
import signal
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web_ui_server import WebUIServer


class ServeEntry:
    """Parses the console command line and starts the web UI server.

    The access key comes from the TOMOVIC_ACCESS_KEY environment variable rather
    than the command line, because every user of a shared server can read the
    command line of any process. The variable is removed from the environment
    once read, so the jobs the console launches do not inherit it.

    Attributes:
        parser : Argument parser holding the host, port and project-root options.
    """

    KEY_VARIABLE = "TOMOVIC_ACCESS_KEY"

    def __init__(self) -> None:
        """Builds the argument parser with the host, port and root options."""
        self.parser = argparse.ArgumentParser(description="TomoVic control console", epilog=f"Set {self.KEY_VARIABLE} to make the console answer only browsers that opened its link http://<address>:<port>/?key=<key>. A --host other than a loopback address requires it.")
        self.parser.add_argument("--host", default="127.0.0.1", help="IPv4 address or host name to listen on; 0.0.0.0 listens on every interface")
        self.parser.add_argument("--port", type=int, default=8765)
        self.parser.add_argument("--root", type=Path, default=None, help="project root the console operates on (jobs, logs, runs); defaults to the repository holding this file")

    def _loopback(self, host: str) -> bool:
        """Returns whether `host` resolves to a loopback address, reachable from this machine only."""
        return ipaddress.ip_address(socket.gethostbyname(host)).is_loopback

    def run(self) -> None:
        """Parses the command line and serves the console until it is stopped.

        SIGUSR1 dumps every thread's stack to stderr, so a request or a cube
        load that hangs can be located with ``kill -USR1 <pid>`` while the
        console keeps running.
        """
        faulthandler.register(signal.SIGUSR1, all_threads=True)

        args       = self.parser.parse_args()
        access_key = os.environ.pop(self.KEY_VARIABLE, "")

        if not access_key and not self._loopback(args.host):
            self.parser.error(f"--host {args.host} lets other machines reach the console; set {self.KEY_VARIABLE} so only its link opens it")

        server = WebUIServer(host=args.host, port=args.port, root=args.root, access_key=access_key)
        server.serve()


if __name__ == "__main__":
    ServeEntry().run()
