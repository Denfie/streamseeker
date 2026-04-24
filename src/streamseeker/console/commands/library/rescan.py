from __future__ import annotations

from collections import Counter

from cleo.commands.command import Command
from cleo.helpers import option

from streamseeker.api.core.library.rescan import rescan_success_log


class LibraryRescanCommand(Command):
    name = "library rescan"
    description = (
        "Rebuild Library entries from ~/.streamseeker/logs/success.log — "
        "useful after migrating older downloads or restoring from a backup."
    )

    options = [
        option("details", "d", "Print every classified entry.", flag=True),
    ]

    def handle(self) -> int:
        report = rescan_success_log()

        if not report.items and not report.skipped:
            self.line("<comment>success.log is empty or missing — nothing to do.</comment>")
            return 0

        by_stream: Counter = Counter()
        by_key: set[str] = set()
        for item in report.items:
            by_stream[item.stream] += 1
            by_key.add(f"{item.stream}::{item.slug}")

        self.line(
            f"<info>Rescanned {len(report.items)} log entries — "
            f"{len(by_key)} unique series/movies restored.</info>"
        )
        for stream, count in sorted(by_stream.items(), key=lambda x: -x[1]):
            self.line(f"  {stream}: {count} entries")

        if self.option("details"):
            for item in report.items:
                label = (
                    f"S{item.season}E{item.episode}" if item.type == "staffel"
                    else f"movie {item.episode}"
                )
                self.line(f"    {item.stream}::{item.slug} — {label}")

        if report.skipped:
            self.line(
                f"\n<comment>{len(report.skipped)} lines could not be classified "
                f"(unknown path layout). Ignored.</comment>"
            )
            if self.option("details"):
                for path in report.skipped[:20]:
                    self.line(f"    {path}")
                if len(report.skipped) > 20:
                    self.line(f"    … and {len(report.skipped) - 20} more")

        self.line(
            "\n<comment>Tip:</comment> run <info>streamseeker library refresh --all</info> "
            "to enrich the rebuilt entries with external metadata and cover art."
        )
        return 0
