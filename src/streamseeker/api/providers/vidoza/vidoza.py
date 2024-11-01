from streamseeker.api.core.exceptions import CacheUrlError
from streamseeker.api.core.request_handler import RequestHandler
from streamseeker.api.providers.provider_base import ProviderBase

from streamseeker.api.core.downloader.standard import DownloaderStandard

from streamseeker.api.core.logger import Logger
logger = Logger().instance()

class VidozaProvider(ProviderBase):
    name = "vidoza"
    title = "Vidoza"
    priority = 20

    def get_download_url(self, url):
        try:
            request = self.request(url)
            request_handler = RequestHandler()
            soup = request_handler.soup(request["plain_html"].decode("utf-8"))
            cache_url = soup.find("source").get("src")
        except Exception as e:
            logger.error(f"ERROR: {e}")
            logger.debug("Trying again...")
            if self.cache_attemps < 5:
                self.cache_attemps += 1
                return self.get_download_url(url)
            raise CacheUrlError(f"Could not get cache url for {self.title}")

        self.cache_attemps = 0
        return cache_url
  
    def download(self, url, file_name):
        try:
            cache_url = self.get_download_url(url)
        except CacheUrlError as e:
            logger.error(f"ERROR: {e}")
            raise CacheUrlError(e)
        
        self._downloader = DownloaderStandard(cache_url, file_name)
        self._downloader.start()

        return self._downloader
