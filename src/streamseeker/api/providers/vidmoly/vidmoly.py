import re

from streamseeker.api.core.exceptions import CacheUrlError
from streamseeker.api.providers.provider_base import ProviderBase
from streamseeker.api.core.downloader.ffmpeg import DownloaderFFmpeg

from streamseeker.api.core.logger import Logger
logger = Logger().instance()


class VidmolyProvider(ProviderBase):
    name = "vidmoly"
    title = "Vidmoly"
    priority = 15

    # Pattern to extract m3u8 URL from the player sources (single or double quotes)
    _SOURCE_PATTERN = re.compile(r'sources:\s*\[\{\s*file:\s*["\'](?P<url>[^"\']+)["\']', re.M)

    def get_download_url(self, url):
        try:
            request = self.request(url)
            html_page = request["plain_html"].decode("utf-8")

            match = self._SOURCE_PATTERN.search(html_page)
            if match:
                cache_url = match.group("url")
                if cache_url and cache_url.startswith("http"):
                    self.cache_attemps = 0
                    return cache_url

        except Exception as e:
            logger.error(f"ERROR: {e}")
            logger.debug("Trying again...")
            if self.cache_attemps < 5:
                self.cache_attemps += 1
                return self.get_download_url(url)

        raise CacheUrlError(f"Could not get cache url for {self.title}")

    def download(self, url, file_name):
        try:
            cache_url = self.get_download_url(url)
        except CacheUrlError as e:
            logger.error(f"ERROR: {e}")
            raise CacheUrlError(e)

        headers = {"Referer": "https://vidmoly.to/"}
        self._downloader = DownloaderFFmpeg(cache_url, file_name, headers=headers)
        self._downloader.start()

        return self._downloader
