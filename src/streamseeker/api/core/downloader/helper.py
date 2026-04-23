import os
from datetime import datetime, timezone

from streamseeker.api.core.helpers import Singleton
from streamseeker.api.core.output_handler import OutputHandler

from streamseeker.api.core.logger import Logger
logger = Logger().instance()

class DownloadHelper(metaclass=Singleton):
    success_log_handler: OutputHandler = None
    error_log_handler: OutputHandler = None

    success_lines = []
    error_lines = []

    def __init__(self):
        self.success_log_handler = OutputHandler(os.sep.join(["logs", "success.log"]))
        self.error_log_handler = OutputHandler(os.sep.join(["logs", "error.log"]))

        self.success_lines = self.success_log_handler.read_lines()
        self.error_lines = self.error_log_handler.read_lines()


    def download_success(self, data) -> None:
        utcTime = datetime.now(timezone.utc)
        try:
            file_size = os.path.getsize(data)
        except OSError:
            file_size = 0
        log_message = f"[{utcTime.astimezone().isoformat()}] {data} :: size={file_size}"

        self.success_lines.append(log_message)
        self.success_log_handler.write_line(log_message)
        self._remove_from_error_log(data)

    def download_error(self, data, url) -> None:
        utcTime = datetime.now(timezone.utc)
        log_message = f"[{utcTime.astimezone().isoformat()}] {data} :: {url}"

        self.error_lines.append(log_message)
        self.error_log_handler.write_line(log_message)

    def is_downloaded(self, file_path) -> bool:
        if not os.path.isfile(file_path):
            return False

        # Check success log for matching entry with size
        for line in self.success_lines:
            if file_path in line:
                # Extract logged size if available
                logged_size = self._parse_size_from_log(line)
                if logged_size is not None and logged_size > 0:
                    actual_size = os.path.getsize(file_path)
                    if actual_size < logged_size:
                        # File is incomplete
                        return False
                return True

        # File exists but not in success log — check if it looks complete
        # (no reference size available, so we can't verify — treat as not downloaded)
        return False

    def _parse_size_from_log(self, line: str) -> int | None:
        """Extract size= value from a success log line."""
        try:
            if ":: size=" in line:
                return int(line.split(":: size=")[-1].strip())
        except (ValueError, IndexError):
            pass
        return None

    def _remove_from_error_log(self, data) -> None:
        readlines = self.error_log_handler.read_lines()
        filtered = [line for line in readlines if line.find(data) == -1]
        if len(filtered) != len(readlines):
            self.error_log_handler.write_lines(filtered, mode='w')
