from __future__ import annotations

import os
import select
import sys
import termios
import tty

from cleo.commands.command import Command
from cleo.io.inputs.string_input import StringInput

from streamseeker.api.core.downloader.manager import DownloadManager
from streamseeker.api.core.downloader.processor import QueueProcessor


class RunCommand(Command):
    name = "run"

    description = "Run Streamseeker to get the interactive mode."

    def handle(self) -> int:
        from streamseeker.utils._compat import get_version
        __version__ = get_version()

        self.line(
            f"""\
<fg=magenta>------------------------------------------------------------------------
---------------------- Streamseeker - Interactive ----------------------
------------------------------------------------------------------------</>

Version: <fg=cyan>{__version__}</>
"""
        )

        manager = DownloadManager()

        # Reset items stuck on "downloading" from a previous interrupted session
        for item in manager.get_queue():
            if item.get("status") == "downloading":
                manager.mark_status(item.get("file_name"), "pending")

        try:
            while True:
                # Clear screen for clean menu
                sys.stdout.write("\033[2J\033[H")
                sys.stdout.flush()

                # Build dynamic menu
                choices = ["Download a movie or show"]
                active = manager.active_count()
                queue = manager.get_queue()
                has_queue = active > 0 or len(queue) > 0

                # Check for pending/failed items that can be started
                startable = [
                    item for item in queue
                    if item.get("status") in ("pending", "failed")
                ]

                if startable:
                    choices.append(f"Start queue ({len(startable)})")

                # Check for manageable items (all except downloading and completed)
                manageable = [
                    item for item in queue
                    if item.get("status") in ("pending", "failed", "skipped", "paused")
                ]

                if manageable:
                    choices.append(f"Manage queue ({len(manageable)})")

                if has_queue:
                    choices.append("View downloads")

                choices.append("About us")
                choices.append("-- Quit --")

                # Show queue status when downloads are active
                if has_queue:
                    summary = manager.queue_summary()
                    self.line(
                        f"<info>[\u2b07 {summary['downloading']} | \u23f3 {summary['pending']} | \u274c {summary['failed']} | \u23ed {summary['skipped']} | \u23f8 {summary['paused']}]</info>"
                    )
                    self.line("")

                search_type = self.choice(
                    "What do you want to do?",
                    choices,
                    attempts=3,
                    default=len(choices) - 1,
                )
                self.line("")

                match search_type:
                    case "Download a movie or show":
                        self.call("download")
                        # Downloads now start in background — jump to view
                        result = self._show_download_view(manager)
                        if result == "quit":
                            return 0
                    case s if s.startswith("Start queue"):
                        self._start_queue(manager, startable)
                        result = self._show_download_view(manager)
                        if result == "quit":
                            return 0
                    case s if s.startswith("Manage queue"):
                        self._manage_queue(manager, manageable)
                    case "View downloads":
                        result = self._show_download_view(manager)
                        if result == "quit":
                            return 0
                    case "About us":
                        self.call("about")
                    case "-- Quit --":
                        self._graceful_quit(manager)
                        return 0
                    case _:
                        self.line("Invalid choice")

                self.line("")
        except (KeyboardInterrupt, EOFError):
            self.line("")
            self.line("<comment>Interrupted.</comment>")
            return 0

        return 0

    def _manage_queue(self, manager: DownloadManager, items: list[dict]) -> None:
        """Let user manage skipped/paused/failed items: retry, pause, resume, remove."""
        import re as _re

        status_markers = {"pending": "\u23f3", "skipped": "\u23ed", "paused": "\u23f8", "failed": "\u274c"}

        # Build choice list
        item_choices = []
        for item in items:
            name = os.path.basename(item.get("file_name", "unknown"))
            status = item.get("status", "")
            marker = status_markers.get(status, "?")
            reason = ""
            if item.get("skip_reason"):
                reason = f" \u2014 {_re.sub(r'<[^>]+>', '', str(item['skip_reason']))}"
            elif item.get("last_error"):
                reason = f" \u2014 {_re.sub(r'<[^>]+>', '', str(item['last_error']))}"
            item_choices.append(f"{marker} [{status}] {name}{reason}")
        item_choices.append("-- Back --")

        selected = self.choice(
            "Select an item to manage:",
            item_choices,
            attempts=3,
            default=len(item_choices) - 1,
        )
        self.line("")

        if selected == "-- Back --":
            return

        idx = item_choices.index(selected)
        item = items[idx]
        file_name = item.get("file_name", "")
        status = item.get("status", "")

        # Build action menu based on current status
        actions = []
        if status == "pending":
            actions.append("Pause")
        elif status in ("skipped", "failed"):
            actions.append("Retry with new settings")
            actions.append("Resume (set to pending)")
            actions.append("Pause")
        elif status == "paused":
            actions.append("Resume (set to pending)")
            actions.append("Retry with new settings")
        actions.append("Remove from queue")
        actions.append("-- Back --")

        action = self.choice(
            f"Action for {os.path.basename(file_name)}:",
            actions,
            attempts=3,
            default=len(actions) - 1,
        )
        self.line("")

        match action:
            case "Resume (set to pending)":
                manager.mark_status(file_name, "pending", attempts=0, last_error=None, skip_reason=None)
                self.line("<info>Set to pending. Will be picked up by the processor.</info>")
            case "Pause":
                manager.mark_status(file_name, "paused")
                self.line("<info>Paused.</info>")
            case "Remove from queue":
                manager._remove_from_queue(file_name)
                if file_name and os.path.isfile(file_name):
                    try:
                        os.remove(file_name)
                    except OSError:
                        pass
                self.line("<info>Removed from queue.</info>")
            case "Retry with new settings":
                self._retry_with_new_settings(manager, item)
            case _:
                return

    def _retry_with_new_settings(self, manager: DownloadManager, item: dict) -> None:
        """Re-queue an item with new language/provider settings."""
        from streamseeker.api.handler import StreamseekerHandler

        handler = StreamseekerHandler()
        stream_name = item.get("stream_name", "")
        name = item.get("name", "")
        type_ = item.get("type", "")
        season = item.get("season", 0)
        episode = item.get("episode", 0)

        self.line(f"  Stream: {stream_name}  |  Language: {item.get('language')}  |  Provider: {item.get('preferred_provider')}")
        self.line("")

        try:
            details = handler.search_details(stream_name, name, type_, season, episode)
        except Exception as e:
            self.line(f"<error>Could not fetch details: {e}</error>")
            return

        languages = details.get("languages", {})
        providers = details.get("providers", {})

        if not languages:
            self.line("<error>No languages available for this item.</error>")
            return

        # Pick language
        lang_list = [lang.get("title", k) for k, lang in languages.items()]
        lang_list.append("-- Cancel --")
        lang_choice = self.choice("Choose a language:", lang_list, attempts=3, default=len(lang_list) - 1)
        self.line("")
        if lang_choice == "-- Cancel --":
            return

        new_language = None
        for key, lang in languages.items():
            if lang.get("title") == lang_choice:
                new_language = key
                break

        if not providers:
            self.line("<error>No providers available.</error>")
            return

        # Pick provider
        prov_list = [prov.get("title", k) for k, prov in providers.items()]
        prov_list.append("-- Cancel --")
        prov_choice = self.choice("Choose a provider:", prov_list, attempts=3, default=len(prov_list) - 1)
        self.line("")
        if prov_choice == "-- Cancel --":
            return

        new_provider = None
        for key, prov in providers.items():
            if prov.get("title") == prov_choice:
                new_provider = key
                break

        # Remove old, clean up file
        old_file = item.get("file_name", "")
        manager._remove_from_queue(old_file)
        if old_file and os.path.isfile(old_file):
            try:
                os.remove(old_file)
            except OSError:
                pass

        # Re-enqueue
        handler.enqueue_single(stream_name, new_provider, name, new_language, type_, season, episode)
        self.line("<info>Re-queued with new settings.</info>")

        processor = QueueProcessor()
        if not processor.is_running():
            processor.start(config=handler.config)

    def _start_queue(self, manager: DownloadManager, items: list[dict]) -> None:
        """Start the queue processor to download pending items."""
        from streamseeker.api.handler import StreamseekerHandler
        processor = QueueProcessor()
        if not processor.is_running():
            config = StreamseekerHandler().config
            processor.start(config=config)
            self.line(f"<info>Queue processor started with {len(items)} item(s).</info>")
        else:
            self.line("<comment>Queue processor is already running.</comment>")

    def _show_download_view(self, manager: DownloadManager) -> str | None:
        """Live auto-refreshing download view. Press m for menu, q to quit."""
        fd = sys.stdin.fileno()
        try:
            old_settings = termios.tcgetattr(fd)
        except termios.error:
            return self._show_download_view_blocking(manager)

        try:
            tty.setcbreak(fd)
            # Clear screen, hide cursor
            sys.stdout.write("\033[2J\033[H\033[?25l")
            sys.stdout.flush()
            while True:
                self._render_view(manager)

                # Wait up to 333ms for keypress
                ready, _, _ = select.select([sys.stdin], [], [], 0.333)
                if ready:
                    key = sys.stdin.read(1).lower()
                    if key == "m":
                        break
                    elif key == "q":
                        sys.stdout.write("\033[?25h")  # Show cursor
                        sys.stdout.flush()
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                        self._graceful_quit(manager)
                        return "quit"
        except (KeyboardInterrupt, EOFError):
            pass
        finally:
            sys.stdout.write("\033[?25h")  # Show cursor
            sys.stdout.flush()
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        return None

    def _show_download_view_blocking(self, manager: DownloadManager) -> str | None:
        """Fallback download view for non-terminal environments."""
        while True:
            self._render_view(manager)
            key = self.ask("<comment>[m] Menu  [q] Quit  [Enter] Refresh:</comment> ")
            key = (key or "").strip().lower()
            if key == "m":
                break
            elif key == "q":
                self._graceful_quit(manager)
                return "quit"
        return None

    def _render_view(self, manager: DownloadManager) -> None:
        """Render the download view flicker-free by overwriting lines in place."""
        import re as _re

        summary, progress, queue = self._view_data(manager)

        # Build all lines first
        lines: list[str] = []
        lines.append("\033[36m--- Download Progress ---\033[0m")
        lines.append(
            f"  \u2b07 {summary['downloading']}  |  "
            f"\u23f3 {summary['pending']}  |  "
            f"\u274c {summary['failed']}  |  "
            f"\u23ed {summary['skipped']}  |  "
            f"\u23f8 {summary['paused']}"
        )
        lines.append("")

        if progress:
            lines.append("\033[1mActive:\033[0m")
            for p in progress:
                lines.append(f"  {self._render_bar(p)}")
            lines.append("")

        # Queue items grouped by status
        by_status: dict[str, list] = {}
        for item in queue:
            s = item.get("status", "pending")
            by_status.setdefault(s, []).append(item)

        # Status config: (label, detail_key, grouped)
        # grouped=True: collapse items by series name \u2192 "Series Title (count)"
        # grouped=False: list each item individually (with optional detail)
        status_labels = [
            ("downloading", "\033[33m\u2b07 Downloading\033[0m", "", True),
            ("pending",     "\033[37m\u23f3 Pending\033[0m",     "", True),
            ("failed",      "\033[31m\u274c Failed\033[0m",      "last_error", False),
            ("skipped",     "\033[90m\u23ed Skipped\033[0m",     "skip_reason", True),
            ("paused",      "\033[34m\u23f8 Paused\033[0m",      "skip_reason", True),
            ("completed",   "\033[32m\u2705 Completed\033[0m",   "", True),
        ]

        max_detail_rows = 5  # cap per ungrouped status to prevent overflow

        for status_key, label, detail_key, grouped in status_labels:
            items = by_status.get(status_key, [])
            if not items:
                continue
            lines.append(f"{label} ({len(items)}):")

            if grouped:
                for title, count in self._group_by_series(items):
                    suffix = f" ({count})" if count > 1 else ""
                    lines.append(f"  {title}{suffix}")
            else:
                for item in items[:max_detail_rows]:
                    name = os.path.basename(item.get("file_name", "unknown"))
                    detail = ""
                    if detail_key and item.get(detail_key):
                        raw = str(item.get(detail_key, ""))
                        detail = f" \u2014 {_re.sub(r'<[^>]+>', '', raw)}"
                    attempts = item.get("attempts", 0)
                    attempt_suffix = f" (x{attempts})" if attempts > 0 else ""
                    lines.append(f"  {name}{attempt_suffix}{detail}")
                remaining = len(items) - max_detail_rows
                if remaining > 0:
                    lines.append(f"  \033[90m\u2026 and {remaining} more\033[0m")
            lines.append("")

        lines.append("\033[90m[m] Menu  [q] Quit\033[0m")

        # Move cursor to top-left, overwrite each line, clear leftover content
        buf = "\033[H"  # Cursor home (no clear!)
        for line in lines:
            buf += f"{line}\033[K\n"  # Write line + clear rest of that line
        buf += "\033[J"  # Clear everything below the last line
        sys.stdout.write(buf)
        sys.stdout.flush()

    def _render_bar(self, p: dict) -> str:
        """Render a single progress bar as plain text."""
        name = p["name"]
        pct = p["pct"]
        total = p["total"]
        n = p["n"]
        unit = p["unit"]

        bar_width = 30
        filled = int(bar_width * pct / 100)
        bar = "\u2588" * filled + "\u2591" * (bar_width - filled)

        if unit == "B":
            n_str = self._format_bytes(n)
            total_str = self._format_bytes(total)
            return f"{name}: [{bar}] {pct:5.1f}%  {n_str}/{total_str}"
        elif unit == "s":
            return f"{name}: [{bar}] {pct:5.1f}%  {n:.0f}/{total:.0f}s"
        else:
            return f"{name}: [{bar}] {pct:5.1f}%"

    def _view_data(self, manager: DownloadManager) -> tuple[dict, list, list]:
        """Return (summary, progress, queue) for the render loop.

        Poll the daemon when it's alive, else read the local manager directly.
        Polling happens each render tick (~333ms); for a localhost endpoint
        that's cheap enough, and we dodge SSE plumbing inside a terminal
        non-blocking loop.
        """
        from streamseeker.api.core import daemon_client

        if daemon_client.is_daemon_running():
            try:
                status = daemon_client.status()
                queue = daemon_client.queue_list()
                return status.get("summary", {}), status.get("progress", []), queue
            except Exception:
                # One-off hiccup — fall through to local read
                pass
        return manager.queue_summary(), manager.get_progress(), manager.get_queue()

    @staticmethod
    def _group_by_series(items: list[dict]) -> list[tuple[str, int]]:
        """Group queue items by series name, preserving first-seen order.

        Returns a list of (display_title, count) tuples. The title is derived
        from the item's ``name`` field (slug) and prettified for display.
        """
        order: list[str] = []
        counts: dict[str, int] = {}
        titles: dict[str, str] = {}
        for item in items:
            slug = item.get("name") or os.path.splitext(os.path.basename(item.get("file_name", "unknown")))[0]
            if slug not in counts:
                order.append(slug)
                counts[slug] = 0
                titles[slug] = slug.replace("-", " ").replace("_", " ").strip().title() or slug
            counts[slug] += 1
        return [(titles[s], counts[s]) for s in order]

    @staticmethod
    def _format_bytes(b: float) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if b < 1024:
                return f"{b:.1f}{unit}"
            b /= 1024
        return f"{b:.1f}TB"

    def _graceful_quit(self, manager: DownloadManager) -> None:
        QueueProcessor().stop()
        active = manager.active_count()
        if active > 0:
            wait = self.confirm(
                f"{active} download(s) running. Wait for them to finish?",
                default=False,
            )
            if wait:
                self.line("<comment>Waiting for downloads...</comment>")
                manager.wait_all()
                self.line("<info>All downloads completed.</info>")
            else:
                self.line("<comment>Unfinished downloads remain in the queue.</comment>")
                self.line("<comment>Run 'make retry' to resume later.</comment>")

    def call(self, name: str, args: str | None = None) -> int:
        """Call another command, preserving the interactive input stream."""
        assert self.application is not None
        command = self.application.get(name)
        string_input = StringInput(args or "")
        string_input.set_stream(sys.stdin)
        return self.application._run_command(
            command, self._io.with_input(string_input)
        )
