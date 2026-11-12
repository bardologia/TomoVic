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

    With --unix-socket the console listens on a socket file only its owner can
    open, instead of a TCP port, which an SSH tunnel such as
    ``ssh -L 18765:/tmp/tomovic.sock server`` then brings to another computer.

    Attributes:
        parser : Argument parser holding the host, port, socket, project-root and workspace options.
    """

    KEY_VARIABLE = "TOMOVIC_ACCESS_KEY"
    LOCAL_HOST   = "127.0.0.1"
    DEFAULT_PORT = 8765

    def __init__(self) -> None:
        """Builds the argument parser with the host, port, socket and root options."""
        self.parser = argparse.ArgumentParser(description="TomoVic control console", epilog=f"Set {self.KEY_VARIABLE} to make the console answer only browsers that opened its link http://<address>:<port>/?key=<key>. A --host other than a loopback address requires it.")
        self.parser.add_argument("--host", default=None, help=f"IPv4 address or host name to listen on, default {self.LOCAL_HOST}; 0.0.0.0 listens on every interface")
        self.parser.add_argument("--port", type=int, default=None, help=f"TCP port to listen on, default {self.DEFAULT_PORT}")
        self.parser.add_argument("--unix-socket", type=Path, default=None, help="listen on this Unix socket, created with mode 0600, instead of a TCP port; excludes --host and --port")
        self.parser.add_argument("--root", type=Path, default=None, help="project root the console operates on (jobs, logs, runs); defaults to the repository holding this file")
        self.parser.add_argument("--workspace", type=Path, default=None, metavar="PATH", help="folder where TomoVis imports become runs the TomoVic tools read; default <repo root>/workspace")

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

        if args.unix_socket and (args.host is not None or args.port is not None):
            self.parser.error("--unix-socket replaces --host and --port; give one or the other")

        host = self.LOCAL_HOST if args.host is None else args.host
        port = self.DEFAULT_PORT if args.port is None else args.port

        if not access_key and not args.unix_socket and not self._loopback(host):
            self.parser.error(f"--host {host} lets other machines reach the console; set {self.KEY_VARIABLE} so only its link opens it")

        server = WebUIServer(host=host, port=port, root=args.root, access_key=access_key, unix_socket=args.unix_socket, workspace=args.workspace)
        server.serve()


if __name__ == "__main__":
    ServeEntry().run()
