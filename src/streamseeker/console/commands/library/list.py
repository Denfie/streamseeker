from __future__ import annotations

from cleo.commands.command import Command

from streamseeker.api.core.library_backend import LibraryBackend
from streamseeker.console.commands._library_shared import format_row


class LibraryListCommand(Command):
    name = "library list"
    description = "List all series/movies in the Library."

    def handle(self) -> int:
        rows = LibraryBackend().library_list()
        if not rows:
            self.line("<comment>Library is empty.</comment>")
            return 0
        self.line(f"<info>Library ({len(rows)}):</info>")
        for row in sorted(rows, key=lambda r: (r.get("title") or "").lower()):
            self.line(format_row(row))
        return 0
