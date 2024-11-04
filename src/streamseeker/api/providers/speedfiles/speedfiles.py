import re
import time
import random
from packaging.version import Version

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By

from urllib.parse import urlparse

from streamseeker.api.core.exceptions import CacheUrlError
from streamseeker.api.core.request_handler import RequestHandler
from streamseeker.api.providers.provider_base import ProviderBase

from streamseeker.api.core.downloader.standard import DownloaderStandard

from streamseeker.api.core.logger import Logger
logger = Logger().instance()

class SpeedfilesProvider(ProviderBase):
    name = "speedfiles"
    title = "SpeedFiles"
    priority = 50

    def get_download_url(self, url):
        try:
            options = webdriver.ChromeOptions()
            
            min_version_check = self._min_version("76.0.0")
            if min_version_check:
                options.headless = True
            else:
                options.add_argument('headless')

            options.add_argument('window-size=1920x1080')
            options.add_argument("disable-gpu")

            driver = webdriver.Chrome(options=options)
            driver.get(url)
            element = driver.find_element(By.TAG_NAME, 'video')
            cache_link  = element.get_attribute('src')
            driver.quit()

            logger.info(f"Cache link: {cache_link}")
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
    
    def _min_version(self, version: str) -> bool:
        # if version is higher than given version return True
        driver = webdriver.Chrome()
        if 'browserVersion' in driver.capabilities:
            chrome_version  = driver.capabilities['browserVersion']
        else:
            chrome_version = driver.capabilities['version']
        driver.quit()

        if Version(version) < Version(chrome_version):    
            return True
        return False
    