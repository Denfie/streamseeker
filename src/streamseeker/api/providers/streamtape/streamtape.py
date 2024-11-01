import re

from streamseeker.api.core.exceptions import CacheUrlError
from streamseeker.api.providers.provider_base import ProviderBase

from streamseeker.api.core.downloader.standard import DownloaderStandard

from streamseeker.api.core.logger import Logger
logger = Logger().setup(__name__)

class StreamtapeProvider(ProviderBase):
    name = "streamtape"
    title = "Streamtape"
    priority = 40

    def get_download_url(self, url):
        STREAMTAPE_PATTERN = re.compile(r'get_video\?id=[^&\'\s]+&expires=[^&\'\s]+&ip=[^&\'\s]+&token=[^&\'\s]+\'')
        try:
            request = self.request(url)
            html_page = request.get("plain_html").decode("utf-8")
            
            cache_link = STREAMTAPE_PATTERN.search(html_page)
            if cache_link is None:
                raise Exception("Could not find cache link")
            cache_link = "https://" + self.name + ".com/" + cache_link.group()[:-1]
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
    