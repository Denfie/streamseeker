from __future__ import annotations

from cleo.commands.command import Command
from cleo.helpers import argument, option

from streamseeker.api.core.library import LibraryStore
from streamseeker.api.core.library.store import KIND_LIBRARY
from streamseeker.api.core.metadata.resolver import MetadataResolver
from streamseeker.console.commands._library_shared import format_key


class LibraryRefreshCommand(Command):
    name = "library refresh"
    description = "Fetch external metadata (TMDb/AniList) and covers for Library entries."

    arguments = [
        argument("stream", "Stream name (omit with --all).", optional=True),
        argument("slug", "Series/movie slug (omit with --all).", optional=True),
    ]
    options = [
        option("all", "a", "Refresh every Library entry.", flag=True),
        option("missing", "m", "Only refresh entries that lack external metadata.", flag=True),
    ]

    def handle(self) -> int:
        resolver = MetadataResolver()
        store = LibraryStore()

        if self.option("all") or self.option("missing"):
            rows = store.list(KIND_LIBRARY)
            if not rows:
                self.line("<comment>Library is empty.</comment>")
                return 0
            if self.option("missing"):
                rows = [
                    row for row in rows
                    if not (store.get(KIND_LIBRARY, row["key"]) or {}).get("external")
                ]
                if not rows:
                    self.line("<info>All entries already have metadata — nothing to do.</info>")
                    return 0
            successes = 0
            for row in rows:
                key = row["key"]
                self.line(f"  {key} …")
                if resolver.enrich(key):
                    successes += 1
            self.line(f"<info>Refreshed {successes}/{len(rows)} entries.</info>")
            return 0

        stream = self.argument("stream")
        slug = self.argument("slug")
        if not stream or not slug:
            self.line("<error>Pass <stream> <slug> or use --all.</error>")
            return 2

        key = format_key(stream, slug)
        ok = resolver.enrich(key)
        if ok:
            self.line(f"<info>Refreshed:</info> {key}")
            return 0
        self.line(f"<comment>No changes (missing entry, no provider, or no match):</comment> {key}")
        return 1
