"""API routes serving the curated content and model-note libraries.

One generic router exposes a content library under a fixed section path, another
serves model families and their notes, and the backbone variant adds the head
catalog to the family listing.
"""

from __future__ import annotations

from model_library_base import ModelNoteLibrary
from routers.dispatch   import HttpExchange, RouteTable, SubRouter


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


class ModelLibraryRouter(SubRouter):
    """Serves a model-note library: the family listing and one note per model.

    Attributes:
        section: API path this router answers on.
        library: Model note library backing the responses.
    """

    def __init__(self, section: str, library: ModelNoteLibrary) -> None:
        """Stores the section and note library, then declares the routes."""
        self.section = section
        self.library = library

        super().__init__((section,))

    def declare(self, table: RouteTable) -> None:
        """Registers the family listing and the per-model note route."""
        table.add("GET", self.section, self.families)
        table.wildcard("GET", f"{self.section}/", "/note", self.note)

    def families(self, exchange: HttpExchange) -> None:
        """Answers with the model families collected from the library."""
        exchange.send_json({"families": self.library.collect()})

    def note(self, exchange: HttpExchange, key: str) -> None:
        """Answers with one model's note, or 404 when the key is unknown."""
        note = self.library.note(key)
        if note is None:
            exchange.send_json({"error": "not found"}, 404)
            return

        exchange.send_json(note)


class BackboneRouter(ModelLibraryRouter):
    """Model library router that also exposes the prediction heads of the backbone zoo."""

    def families(self, exchange: HttpExchange) -> None:
        """Answers with the backbone families together with the available heads."""
        exchange.send_json({"families": self.library.collect(), "heads": self.library.heads()})
