import os
from datetime import datetime, timezone 

from streamseeker.api.core.helpers import Singleton
from streamseeker.api.core.output_handler import OutputHandler

from streamseeker.api.core.logger import Logger
logger = Logger().setup(__name__)

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
        log_message = f"[{utcTime.astimezone().isoformat()}] {data}"

        self.success_lines.append(log_message)
        self.success_log_handler.write_line(log_message)
        self._remove_from_error_log(data)

    def download_error(self, data, url) -> None:
        utcTime = datetime.now(timezone.utc)
        log_message = f"[{utcTime.astimezone().isoformat()}] {data} :: {url}"

        self.error_lines.append(log_message)
        self.error_log_handler.write_line(log_message)

    def is_downloaded(self, file_path) -> bool:
        file_exists = os.path.isfile(file_path)

        found = False
        for line in self.success_lines:
            if line.find(file_path) != -1:
                found = True
                break

        if file_exists and not found:
            self.download_success(file_path)
            return True

        return found
    
    def _remove_from_error_log(self, data) -> None:
        readlines = self.error_log_handler.read_lines()
        for line in readlines:
            if line.find(data) != -1:
                readlines.remove(line)
        self.error_log_handler.write_lines(readlines, mode='w')