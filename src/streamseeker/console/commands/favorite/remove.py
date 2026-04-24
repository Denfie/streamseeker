from __future__ import annotations

from cleo.commands.command import Command
from cleo.helpers import argument

from streamseeker.api.core.library_backend import LibraryBackend
from streamseeker.console.commands._library_shared import format_key


class FavoriteRemoveCommand(Command):
    name = "favorite remove"
    description = "Remove a favorite by stream and slug."

    arguments = [
        argument("stream", "Stream name."),
        argument("slug", "Series/movie slug."),
    ]

    def handle(self) -> int:
        stream = self.argument("stream")
        slug = self.argument("slug")
        key = format_key(stream, slug)
        removed = LibraryBackend().favorites_remove(key)
        if removed:
            self.line(f"<info>Removed favorite:</info> {key}")
            return 0
        self.line(f"<comment>No favorite found for:</comment> {key}")
        return 1
