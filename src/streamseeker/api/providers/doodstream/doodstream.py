import re
import time
import random

from urllib.parse import urlparse

from streamseeker.api.core.exceptions import CacheUrlError
from streamseeker.api.core.request_handler import RequestHandler
from streamseeker.api.providers.provider_base import ProviderBase

from streamseeker.api.core.downloader.standard import DownloaderStandard

from streamseeker.api.core.logger import Logger
logger = Logger().instance()

class DoodstreamProvider(ProviderBase):
    name = "doodstream"
    title = "Doodstream"
    priority = 30

    def get_download_url(self, url):
        DOODSTREAM_PATTERN_URL = re.compile(r"'(?P<url>/pass_md5/[^'.*]*)'")
        DOODSTREAM_PATTERN_TOKEN = re.compile(r"token=(?P<token>[^&.*]*)&")
        try:
            request = self.request(url)
            html_page = request.get("plain_html").decode("utf-8")

            match_url = DOODSTREAM_PATTERN_URL.search(html_page)
            match_token = DOODSTREAM_PATTERN_TOKEN.search(html_page)

            if match_url and match_token:
                parsed_url = urlparse(request.get("referer"))
                prefetch_request = self.request(f"{parsed_url.scheme}://{parsed_url.netloc}" + match_url.group('url'), {
                    "Referer": request.get("referer"),
                })
                req_body = prefetch_request.get("plain_html").decode("utf-8")
                hash = self._create_doodstream_url_hash()
                cache_link = f"{req_body}{hash}?token={match_token.group('token')}&expiry={self._current_milli_time()}"
        except Exception as e:
            logger.error(f"ERROR: {e}")
            logger.debug("Trying again...")
            if self.cache_attemps < 5:
                self.cache_attemps += 1
                return self.get_download_url(url)
            raise CacheUrlError(f"Could not get cache url for {self.title}")

        self.cache_attemps = 0
        return cache_link
  
    def download(self, url, file_name):
        try:
            cache_url = self.get_download_url(url)
        except CacheUrlError as e:
            logger.error(f"ERROR: {e}")
            raise CacheUrlError(e)
        
        self._downloader = DownloaderStandard(cache_url, file_name)
        self._downloader.start()

        return self._downloader

    def _current_milli_time(self):
        return round(time.time() * 1000)

    def _create_doodstream_url_hash(self, count:int=10):
        return ''.join(random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789') for i in range(count))