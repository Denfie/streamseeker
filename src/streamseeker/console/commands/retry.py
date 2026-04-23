from __future__ import annotations

from cleo.commands.command import Command

from streamseeker.api.core.downloader.manager import DownloadManager
from streamseeker.api.core.downloader.helper import DownloadHelper

from streamseeker.api.core.logger import Logger
logger = Logger().instance()


class RetryCommand(Command):
    name = "retry"

    description = "Retry failed or interrupted downloads from the queue."

    def handle(self) -> int:
        from streamseeker.api.core.downloader.processor import QueueProcessor
        from streamseeker.api.handler import StreamseekerHandler

        manager = DownloadManager()
        queue = manager.get_queue()

        if not queue:
            self.line("<info>No pending downloads in the queue.</info>")
            return 0

        helper = DownloadHelper()

        # Filter and show status
        pending = []
        for item in queue:
            status = item.get("status", "pending")
            if status == "completed":
                continue
            if status == "skipped":
                continue
            if helper.is_downloaded(item.get("file_name", "")):
                manager.report_success(item.get("file_name"))
                continue
            # Reset failed items to pending
            if status == "failed":
                manager.mark_status(item.get("file_name"), "pending", last_error=None)
            pending.append(item)

        if not pending:
            self.line("<info>All queued downloads are already completed.</info>")
            DownloadManager.clear_queue()
            return 0

        self.line(f"<info>Found {len(pending)} download(s) to process:</info>")
        self.line("")
        for item in pending:
            attempts = item.get("attempts", 0)
            status = item.get("status", "pending")
            name = item.get("file_name", "unknown")
            marker = "\u274c" if status == "failed" else "\u23f3"
            self.line(f"  {marker} {name} (attempts: {attempts})")
        self.line("")

        if not self.confirm("Start processing?", default=True):
            return 0

        config = StreamseekerHandler().config
        processor = QueueProcessor()
        processor.start(config=config)
        self.line("<info>Queue processor started.</info>")

        return 0
