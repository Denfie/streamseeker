import os
import time

from http import HTTPStatus
from threading import Thread
from urllib.parse import urlparse
from requests import Session
from requests.exceptions import HTTPError

from tqdm.auto import tqdm

from streamseeker.api.core.downloader.helper import DownloadHelper
from streamseeker.api.core.downloader.manager import DownloadManager
from streamseeker.api.core.exceptions import DownloadError

from streamseeker.api.core.logger import Logger
logger = Logger().instance()

class DownloaderStandard:
    retries = 3
    retry_codes = [
        HTTPStatus.TOO_MANY_REQUESTS,
        HTTPStatus.INTERNAL_SERVER_ERROR,
        HTTPStatus.BAD_GATEWAY,
        HTTPStatus.SERVICE_UNAVAILABLE,
        HTTPStatus.GATEWAY_TIMEOUT,
    ]

    def __init__(self, url, file_name, headers: dict={"User-Agent": "Mozilla/5.0"}):
        self.url = url
        self.file_name = file_name
        self.parsed_url = urlparse(url)
        self.session = Session()
        self._manager = DownloadManager()
        if not headers.get("Referer"):
            headers['Referer'] = f"{self.parsed_url.scheme}://{self.parsed_url.netloc}"

        logger.debug(f"Headers: {headers}")
        self.session.headers.update(headers)

    def start(self):
        self.thread = Thread(target=self._download, args=(self.url, self.file_name), daemon=True)
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

    def _download(self, url: str, path: str):
        helper = DownloadHelper()
        display_name = os.path.basename(path)
        for i in range(self.retries):
            try:
                self._download_file(url, path)
                helper.download_success(path)
                self._manager.report_success(path)
                logger.info(f"\u2705 {display_name}")
                return
            except HTTPError as exc:
                code = exc.response.status_code

                if code in self.retry_codes:
                    if i < self.retries - 1:
                        logger.warning(f"\u26a0\ufe0f  {display_name} \u2014 HTTP {code}, Retry {i + 2}/{self.retries}")
                        time.sleep(20)
                        continue

                logger.error(f"Server error bei {path}. Bitte sp\u00e4ter erneut versuchen.")
                helper.download_error(path, url)
                self._manager.report_failure(path)
                logger.error(f"\u274c {display_name} \u2014 Verarbeitung fehlgeschlagen (HTTP {code})")
                return
            except Exception:
                pass

        # All retries exhausted
        helper.download_error(path, url)
        self._manager.report_failure(path)
        logger.error(f"\u274c {display_name} \u2014 Verarbeitung nach {self.retries} Versuchen fehlgeschlagen")

    def _download_file(self, url: str, path: str):
        file_name = os.path.basename(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        pos = self._manager.acquire_position()
        try:
            with self.session.get(url, stream=True) as response:
                response.raise_for_status()
                total = int(response.headers.get("Content-Length", 0))

                from streamseeker.api.core.downloader.manager import _devnull
                pbar = tqdm(
                    total=total,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    file=_devnull,
                    leave=False,
                )
                self._manager.register_bar(pbar, file_name)
                with open(path, "wb") as file:
                    for chunk in response.iter_content(chunk_size=4096):
                        file.write(chunk)
                        pbar.update(len(chunk))

                self._manager.unregister_bar(file_name)
                pbar.close()
                if os.path.getsize(path) < total:
                    content_length = response.headers.get("Content-Length", 0)
                    raise DownloadError(f"Filesize doesn't match {os.path.getsize(path)} != {content_length}")
        finally:
            self._manager.release_position(pos)
