"""API routes serving the curated content libraries.

One generic router exposes a content library under a fixed section path.
"""

from __future__ import annotations

from routers.dispatch import HttpExchange, RouteTable, SubRouter


class ContentLibraryRouter(SubRouter):
    """Serves one curated content library under a fixed API section.

    Attributes:
        section: API path this router answers on.
        library: Library object exposing a `collect` method.
        envelope: Key the collected payload is wrapped in, empty to send it bare.
    """

    def __init__(self, section: str, library, envelope: str = "") -> None:
        """Stores the section, library and envelope key, then declares the route."""
        self.section  = section
        self.library  = library
        self.envelope = envelope

        super().__init__((section,))

    def declare(self, table: RouteTable) -> None:
        """Registers the single GET route on the configured section path."""
        table.add("GET", self.section, self.content)

    def content(self, exchange: HttpExchange) -> None:
        """Answers with the collected library content, wrapped in the envelope key when set."""
        collected = self.library.collect()
        exchange.send_json({self.envelope: collected} if self.envelope else collected)
