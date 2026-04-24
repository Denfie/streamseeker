from __future__ import annotations

from cleo.commands.command import Command

from streamseeker.api.core.library_backend import LibraryBackend
from streamseeker.console.commands._library_shared import format_row


class FavoriteListCommand(Command):
    name = "favorite list"
    description = "List all favorites."

    def handle(self) -> int:
        rows = LibraryBackend().favorites_list()
        if not rows:
            self.line("<comment>No favorites yet.</comment>")
            return 0
        self.line(f"<info>Favorites ({len(rows)}):</info>")
        for row in sorted(rows, key=lambda r: (r.get("title") or "").lower()):
            self.line(format_row(row))
        return 0
