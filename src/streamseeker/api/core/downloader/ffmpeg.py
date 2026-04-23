import os
import re
import subprocess
import time
from threading import Thread

from tqdm.auto import tqdm

from streamseeker.api.core.downloader.helper import DownloadHelper
from streamseeker.api.core.downloader.manager import DownloadManager

from streamseeker.api.core.logger import Logger
logger = Logger().instance()

class DownloaderFFmpeg:
    ffmpeg_path = "ffmpeg"
    max_retries = 3
    retry_delay = 10  # seconds between retries

    def __init__(self, hls_url, file_name, headers: dict={"User-Agent": "Mozilla/5.0"}):
        self.hls_url = hls_url
        self.file_name = file_name
        self.headers = headers
        self._manager = DownloadManager()

    def handle(self) -> int:
        return 0

    def start(self):
        if not self.is_installed():
            exit(1)

        self.thread = Thread(target=self._download_stream, args=(self.ffmpeg_path, self.hls_url, self.file_name,), daemon=True)
        self.thread.start()
        self._manager.register_thread(self.thread, os.path.basename(self.file_name))

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
            subprocess.run([self.ffmpeg_path, "-version"], check=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        except FileNotFoundError:
            logger.error("<fg=red>FFmpeg is not installed.</> Please install FFmpeg and try again. You can download it at <fg=cyan>https://ffmpeg.org/</>")
            return False
        except subprocess.CalledProcessError:
            logger.error("<fg=red>FFmpeg is not installed.</> Please install FFmpeg and try again. You can download it at <fg=cyan>https://ffmpeg.org/</>")
            return False

    def _download_stream(self, ffmpeg_path, hls_url, file_name):
        helper = DownloadHelper()
        display_name = os.path.basename(file_name)
        os.makedirs(os.path.dirname(file_name), exist_ok=True)

        for attempt in range(self.max_retries):
            pos = self._manager.acquire_position()
            try:
                success = self._attempt_download(ffmpeg_path, hls_url, file_name, display_name, pos)
                if success:
                    helper.download_success(file_name)
                    self._manager.report_success(file_name)
                    logger.info(f"\u2705 {display_name}")
                    return
            except Exception:
                pass
            finally:
                self._manager.release_position(pos)

            if attempt < self.max_retries - 1:
                logger.warning(f"\u26a0\ufe0f  {display_name} \u2014 Retry {attempt + 2}/{self.max_retries}")
                time.sleep(self.retry_delay)

        # All retries exhausted
        helper.download_error(file_name, hls_url)
        self._manager.report_failure(file_name)
        logger.error(f"\u274c {display_name} \u2014 Download failed after {self.max_retries} attempts")

    def _attempt_download(self, ffmpeg_path, hls_url, file_name, display_name, pos) -> bool:
        duration = self._probe_duration(hls_url)

        ffmpeg_cmd = [ffmpeg_path, '-i', hls_url, '-c', 'copy', '-y', file_name, '-progress', 'pipe:1', '-nostats']
        process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

        from streamseeker.api.core.downloader.manager import _devnull
        pbar = tqdm(
            total=duration if duration else None,
            unit="s",
            file=_devnull,
            leave=False,
        )
        self._manager.register_bar(pbar, display_name)

        for line in process.stdout:
            line = line.strip()
            if line.startswith("out_time_ms="):
                try:
                    time_ms = int(line.split("=")[1])
                    seconds = time_ms / 1_000_000
                    # Adjust total if ffprobe gave wrong duration
                    if pbar.total and seconds > pbar.total:
                        pbar.total = seconds + 30
                    pbar.n = seconds
                    pbar.refresh()
                except (ValueError, IndexError):
                    pass

        process.wait()
        self._manager.unregister_bar(display_name)
        pbar.close()

        return process.returncode == 0

    def _probe_duration(self, url: str) -> float | None:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", url],
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30,
            )
            return float(result.stdout.strip())
        except Exception:
            return None
