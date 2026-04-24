from __future__ import annotations

from cleo.commands.command import Command
from cleo.helpers import argument

from streamseeker.api.core.library_backend import LibraryBackend
from streamseeker.console.commands._library_shared import format_key


class LibraryShowCommand(Command):
    name = "library show"
    description = "Show full details of a Library entry."

    arguments = [
        argument("stream", "Stream name."),
        argument("slug", "Series/movie slug."),
    ]

    def handle(self) -> int:
        stream = self.argument("stream")
        slug = self.argument("slug")
        key = format_key(stream, slug)
        entry = LibraryBackend().library_get(key)
        if entry is None:
            self.line(f"<error>Not in Library:</error> {key}")
            return 1

        title = entry.get("title") or key
        year = entry.get("year")
        header = f"{title} ({year})" if year else title
        self.line(f"<info>{header}</info>  <comment>[{key}]</comment>")
        if entry.get("url"):
            self.line(f"  URL: {entry['url']}")
        if entry.get("added_at"):
            self.line(f"  Added: {entry['added_at']}")

        seasons = entry.get("seasons", {}) or {}
        if seasons:
            self.line("  <info>Seasons:</info>")
            for season_key in sorted(seasons, key=int):
                s = seasons[season_key]
                downloaded = s.get("downloaded", [])
                total = s.get("episode_count", 0) or 0
                progress = f"{len(downloaded)}/{total}" if total else f"{len(downloaded)}"
                self.line(f"    Season {season_key}: {progress} Ep.")

        movies = (entry.get("movies") or {}).get("downloaded") or []
        if movies:
            self.line(f"  <info>Movies:</info> {movies}")

        external = entry.get("external") or {}
        if external:
            self.line(f"  <info>External sources:</info> {', '.join(external.keys())}")
        return 0
