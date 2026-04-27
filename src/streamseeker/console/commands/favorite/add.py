from __future__ import annotations

from cleo.commands.command import Command
from cleo.helpers import argument

from streamseeker.api.core.library_backend import LibraryBackend
from streamseeker.console.commands._library_shared import format_key


class FavoriteAddCommand(Command):
    name = "favorite add"
    description = "Add a series/movie to the Favorites list."

    arguments = [
        argument("stream", "Stream name (e.g. aniworldto, sto)."),
        argument("slug", "Series/movie slug (e.g. oshi-no-ko)."),
    ]

    def handle(self) -> int:
        stream = self.argument("stream")
        slug = self.argument("slug")
        entry = LibraryBackend().favorites_add(stream, slug)
        self.line(
            f"<info>Added favorite:</info> {entry['title']} "
            f"<comment>[{format_key(stream, slug)}]</comment>"
        )
        return 0
