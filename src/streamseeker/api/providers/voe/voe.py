import re
import os

from streamseeker.api.core.exceptions import CacheUrlError

from streamseeker.api.providers.provider_base import ProviderBase
from streamseeker.api.core.downloader.ffmpeg import DownloaderFFmpeg  

from streamseeker.api.core.logger import Logger
logger = Logger().setup(__name__)

class VoeProvider(ProviderBase):
    name = "voe"
    title = "VOE"
    priority = 10

    def get_download_url(self, url):
        request = self.request(url)
        html_page = request["plain_html"].decode("utf-8")

        VOE_PATTERNS = [re.compile(r"'hls': '(?P<url>.+)'"),
                re.compile(r'prompt\("Node",\s*"(?P<url>[^"]+)"'),
                re.compile(r"window\.location\.href = '([^']+)'")]
        
        try:
            for VOE_PATTERN in VOE_PATTERNS:
                match = VOE_PATTERN.search(html_page)
                if match:
                    if match.group(0).startswith("window.location.href"):
                        logger.debug("Found window.location.href. Redirecting...")
                        return self.get_download_url(match.group(1))
                    cache_url = match.group(1)
                    if cache_url and cache_url.startswith("https://"):
                        self.cache_attemps = 0
                        return cache_url
        except Exception as e:
            logger.error(f"ERROR: {e}")
            logger.info("Trying again...")
            if self.cache_attemps < 5:
                self.cache_attemps += 1
                return self.get_download_url(url)
  
    def download(self, url, file_name):
        try:
            cache_url = self.get_download_url(url)
        except CacheUrlError as e:
            logger.error(f"ERROR: {e}")
            raise CacheUrlError(e)
        
        os.makedirs(os.path.dirname(file_name), exist_ok=True)        
        self._downloader = DownloaderFFmpeg(cache_url, file_name)
        self._downloader.start()

        return self._downloader