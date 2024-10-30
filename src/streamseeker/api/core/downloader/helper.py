import os
from datetime import datetime, timezone 

from streamseeker.api.core.output_handler import OutputHandler

from streamseeker.api.core.logger import Logger
logger = Logger().setup(__name__)

class DownloadHelper:
    success_log_handler: OutputHandler = None
    error_log_handler: OutputHandler = None

    def __init__(self):
        self.success_log_handler = OutputHandler(os.sep.join(["logs", "success.log"]))
        self.error_log_handler = OutputHandler(os.sep.join(["logs", "error.log"]))


    def download_success(self, data) -> None:
        utcTime = datetime.now(timezone.utc)
        log_message = f"[{utcTime.astimezone().isoformat()}] {data}"
        self.success_log_handler.write_line(log_message)
        self._remove_from_error_log(data)

    def download_error(self, data, url) -> None:
        utcTime = datetime.now(timezone.utc)
        log_message = f"[{utcTime.astimezone().isoformat()}] {data} :: {url}"
        self.error_log_handler.write_line(log_message)

    def _remove_from_error_log(self, data) -> None:
        readlines = self.error_log_handler.read_lines()
        for line in readlines:
            if line.find(data) != -1:
                readlines.remove(line)
        self.error_log_handler.write_lines(readlines, mode='w')