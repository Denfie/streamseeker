import platform
import subprocess
from threading import Thread

from streamseeker.api.core.classes.base_class import BaseClass
from streamseeker.api.core.downloader.helper import DownloadHelper

from streamseeker.api.core.logger import Logger
logger = Logger().instance()

class DownloaderFFmpeg(BaseClass):
    ffmpeg_path = "ffmpeg"

    def __init__(self, hls_url, file_name, headers: dict={"User-Agent": "Mozilla/5.0"}):
        super().__init__()
        self.hls_url = hls_url
        self.file_name = file_name
        self.headers = headers

    def handle(self) -> int:
        return 0

    def start(self):
        if not self.is_installed():
            exit(1)
            
        self.thread = Thread(target=self._download_stream, args=(self.ffmpeg_path, self.hls_url, self.file_name,))
        self.thread.start()

        return self.thread

    def join(self):
        if self.is_alive():
            self.thread.join()
        
    def is_alive(self):
        if self.thread is None:
            return False
        return self.thread.is_alive()

    def is_installed(self):
        try:
            subprocess.run([self.ffmpeg_path, "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        except FileNotFoundError:
            logger.error("<fg=red>FFmpeg is not installed. Please install FFmpeg and try again. You can download it at https://ffmpeg.org/</>")
            return False
        except subprocess.CalledProcessError:
            logger.error("<fg=red>FFmpeg is not installed. Please install FFmpeg and try again. You can download it at https://ffmpeg.org/</>")
            return False

    def _download_stream(self, ffmpeg_path, hls_url, file_name):  
        helper = DownloadHelper()
        try:
            logger.info(f"<fg=yellow>Downloading {file_name}...</>")
            ffmpeg_cmd = [ffmpeg_path, '-i', hls_url, '-c', 'copy', file_name]
            if platform.system() == "Windows":
                subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            else:
                subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"<fg=green>Finished download of {file_name}.</>")
            helper.download_success(file_name)
        except subprocess.CalledProcessError as e:
            logger.error(f"<fg=red>Server error. Could not download {file_name}. Please try to download it later.</>")
            helper.download_error(file_name, hls_url)