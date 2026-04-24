from __future__ import annotations

from cleo.commands.command import Command
from cleo.helpers import argument

from streamseeker.api.core.library_backend import LibraryBackend
from streamseeker.console.commands._library_shared import format_row


class LibrarySearchCommand(Command):
    name = "library search"
    description = "Search the Library by title or slug (case-insensitive)."

    arguments = [argument("term", "Search term.")]

    def handle(self) -> int:
        term = self.argument("term")
        rows = LibraryBackend().library_search(term)
        if not rows:
            self.line(f"<comment>No Library entries match {term!r}.</comment>")
            return 0
        self.line(f"<info>Matches ({len(rows)}):</info>")
        for row in rows:
            self.line(format_row(row))
        return 0
