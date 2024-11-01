import os
import time

from http import HTTPStatus
from threading import Thread
from urllib.parse import urlparse
from requests import Session
from requests.exceptions import HTTPError

from tqdm.auto import tqdm

from streamseeker.api.core.downloader.helper import DownloadHelper

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
        if not headers.get("Referer"):
            headers['Referer'] = f"{self.parsed_url.scheme}://{self.parsed_url.netloc}"

        logger.debug(f"Headers: {headers}")
        self.session.headers.update(headers)
    
    def start(self):
        self.thread = Thread(target=self._download, args=(self.url, self.file_name))
        self.thread.start()

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
        for i in range(self.retries):
            try:
                self._download_file(url, path)
                helper.download_success(path)
                break
            except HTTPError as exc:
                code = exc.response.status_code
                
                if code in self.retry_codes:
                    # retry after 20 seconds
                    time.sleep(20)
                    continue
                    
                logger.error(f"Server error. Could not download {path}. Please try to download it later.")
                helper.download_error(path, url)
                raise

    def _download_file(self, url: str, path: str):
        file_name = os.path.basename(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with self.session.get(url, stream=True) as response:
            response.raise_for_status()

            pbar = tqdm(desc=file_name, colour="green", total=int(response.headers.get("Content-Length", 0)), unit="B", unit_scale=True, unit_divisor=1024)
            with open(path, "wb") as file:
                for chunk in response.iter_content(chunk_size=1024):
                    file.write(chunk)
                    pbar.update(len(chunk))

            pbar.close()
            if os.path.getsize(path) >= int(response.headers.get("Content-Length", 0)):
                logger.debug(f"Finished download of {path}.")
            else:
                logger.error(f"Filesize doesn't match {os.path.getsize(path)} != {response.headers.get("Content-Length", 0)}.")
