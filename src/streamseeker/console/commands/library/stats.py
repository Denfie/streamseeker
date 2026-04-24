from __future__ import annotations

from collections import Counter

from cleo.commands.command import Command

from streamseeker.api.core.library_backend import LibraryBackend


class LibraryStatsCommand(Command):
    name = "library stats"
    description = "Summary statistics of the Library."

    def handle(self) -> int:
        rows = LibraryBackend().library_list()
        if not rows:
            self.line("<comment>Library is empty.</comment>")
            return 0

        total_downloaded = sum(r.get("downloaded_count", 0) for r in rows)
        by_stream = Counter(r.get("stream", "?") for r in rows)
        completed = [
            r for r in rows
            if r.get("total_count") and r["downloaded_count"] >= r["total_count"]
        ]

        self.line(f"<info>Library:</info> {len(rows)} entries, {total_downloaded} episodes/movies local")
        self.line("  <info>By stream:</info>")
        for stream, count in sorted(by_stream.items(), key=lambda x: -x[1]):
            self.line(f"    {stream}: {count}")

        top = sorted(rows, key=lambda r: -r.get("downloaded_count", 0))[:5]
        if top:
            self.line("  <info>Most complete:</info>")
            for row in top:
                title = row.get("title") or row.get("slug", "?")
                dl = row.get("downloaded_count", 0)
                total = row.get("total_count", 0)
                progress = f"{dl}/{total}" if total else f"{dl}"
                self.line(f"    {title} — {progress} Ep.")

        self.line(f"  <info>Fully downloaded:</info> {len(completed)}")
        return 0
