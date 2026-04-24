from __future__ import annotations

from cleo.commands.command import Command
from cleo.helpers import argument

from streamseeker.api.core import daemon_client
from streamseeker.api.core.library_backend import LibraryBackend
from streamseeker.console.commands._library_shared import format_key


class FavoritePromoteCommand(Command):
    name = "favorite promote"
    description = "Move a favorite into the Library (keeping its metadata and assets)."

    arguments = [
        argument("stream", "Stream name."),
        argument("slug", "Series/movie slug."),
    ]

    def handle(self) -> int:
        stream = self.argument("stream")
        slug = self.argument("slug")
        key = format_key(stream, slug)
        try:
            entry = LibraryBackend().favorites_promote(key)
        except (FileNotFoundError, daemon_client.DaemonError) as exc:
            if isinstance(exc, daemon_client.DaemonError) and exc.status_code != 404:
                self.line(f"<error>{exc}</error>")
                return 2
            self.line(f"<error>No favorite found for {key}.</error>")
            return 1
        self.line(f"<info>Promoted to Library:</info> {entry.get('title') or key}")
        return 0
