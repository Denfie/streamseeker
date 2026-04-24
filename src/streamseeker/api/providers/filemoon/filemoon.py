import json
import re
import time
from datetime import datetime, timezone

from selenium import webdriver
from selenium.webdriver.common.by import By

from streamseeker import paths
from streamseeker.api.core.exceptions import CacheUrlError
from streamseeker.api.providers.provider_base import ProviderBase
from streamseeker.api.core.downloader.ffmpeg import DownloaderFFmpeg

from streamseeker.api.core.logger import Logger
logger = Logger().instance()


class FilemoonProvider(ProviderBase):
    name = "filemoon"
    title = "Filemoon"
    priority = 45  # Experimental — Filemoon uses Vite SPA, extraction unreliable

    # Patterns to extract m3u8 URL from page source after JS execution
    _URL_PATTERNS = [
        re.compile(r'file\s*:\s*["\'](?P<url>https?://[^"\']+\.m3u8[^"\']*)["\']'),
        re.compile(r'src\s*:\s*["\'](?P<url>https?://[^"\']+\.m3u8[^"\']*)["\']'),
        re.compile(r'source\s*:\s*["\'](?P<url>https?://[^"\']+\.m3u8[^"\']*)["\']'),
        re.compile(r'["\'](?P<url>https?://[^"\']+\.m3u8[^"\']*)["\']'),
    ]

    def get_download_url(self, url):
        driver = None
        debug_info = {
            "url": url,
            "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
            "attempt": self.cache_attemps + 1,
        }

        try:
            options = webdriver.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1920x1080")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            # Mimic real browser
            options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

            driver = webdriver.Chrome(options=options)

            # Set referer via page navigation
            driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {
                "headers": {"Referer": "https://aniworld.to/"}
            })

            driver.get(url)
            time.sleep(5)  # Wait for SPA to render

            page_source = driver.page_source
            debug_info["page_length"] = len(page_source)

            # Collect all script contents for analysis
            scripts = re.findall(r'<script[^>]*>(.*?)</script>', page_source, re.DOTALL)
            debug_info["script_count"] = len(scripts)
            debug_info["scripts_with_content"] = [
                s[:500] for s in scripts if len(s) > 50
            ]

            # Search for video URLs in rendered page
            for pattern in self._URL_PATTERNS:
                match = pattern.search(page_source)
                if match:
                    cache_url = match.group("url")
                    if cache_url and cache_url.startswith("http"):
                        logger.debug(f"Filemoon URL found: {cache_url[:80]}...")
                        debug_info["result"] = "success"
                        debug_info["video_url"] = cache_url
                        self._save_debug(debug_info)
                        self.cache_attemps = 0
                        return cache_url

            # Fallback: video element
            try:
                video = driver.find_element(By.TAG_NAME, "video")
                src = video.get_attribute("src")
                debug_info["video_element_src"] = src
                if src and src.startswith("http"):
                    debug_info["result"] = "success_video_element"
                    self._save_debug(debug_info)
                    self.cache_attemps = 0
                    return src
            except Exception:
                debug_info["video_element_src"] = None

            # Fallback: network requests
            try:
                resources = driver.execute_script(
                    "return window.performance.getEntriesByType('resource').map(e => e.name)"
                )
                debug_info["network_resources"] = [r for r in resources if any(
                    ext in r for ext in ['.m3u8', '.mp4', 'master', 'hls', 'video']
                )]
                for resource in resources:
                    if ".m3u8" in resource:
                        debug_info["result"] = "success_network"
                        self._save_debug(debug_info)
                        self.cache_attemps = 0
                        return resource
            except Exception:
                debug_info["network_resources"] = []

            # Log all iframes for analysis
            try:
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                debug_info["iframes"] = [
                    iframe.get_attribute("src") for iframe in iframes
                ]
            except Exception:
                debug_info["iframes"] = []

            debug_info["result"] = "failed"
            self._save_debug(debug_info)

        except Exception as e:
            logger.error(f"Filemoon error: {e}")
            debug_info["result"] = "exception"
            debug_info["error"] = str(e)
            self._save_debug(debug_info)

            if self.cache_attemps < 3:
                self.cache_attemps += 1
                return self.get_download_url(url)
            raise CacheUrlError(f"Could not get cache url for {self.title}")
        finally:
            if driver:
                driver.quit()

        raise CacheUrlError(f"Could not get cache url for {self.title}")

    def download(self, url, file_name):
        try:
            cache_url = self.get_download_url(url)
        except CacheUrlError as e:
            logger.error(f"ERROR: {e}")
            raise CacheUrlError(e)

        headers = {"Referer": url}
        self._downloader = DownloaderFFmpeg(cache_url, file_name, headers=headers)
        self._downloader.start()

        return self._downloader

    def _save_debug(self, info: dict) -> None:
        """Save debug info to help analyze Filemoon's structure."""
        try:
            debug_file = paths.filemoon_debug_file()
            existing = []
            if debug_file.is_file():
                existing = json.loads(debug_file.read_text())
            # Keep last 20 entries
            existing.append(info)
            existing = existing[-20:]
            debug_file.parent.mkdir(parents=True, exist_ok=True)
            debug_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
        except Exception:
            pass
