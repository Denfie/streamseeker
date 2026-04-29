import re
import os
import base64
import binascii
import json

from typing import Optional, Dict, Any

from streamseeker.api.core.exceptions import CacheUrlError
from streamseeker.api.core.request_handler import RequestHandler

from streamseeker.api.providers.provider_base import ProviderBase
from streamseeker.api.core.downloader.ffmpeg import DownloaderFFmpeg  

from streamseeker.api.core.logger import Logger
logger = Logger().instance()

class VoeProvider(ProviderBase):
    name = "voe"
    title = "VOE"
    priority = 10

    # Pre-compiled junk parts for replacement
    JUNK_PARTS = ["@$", "^^", "~@", "%?", "*~", "!!", "#&"]

    def shift_letters(self, input_str: str) -> str:
        """Apply ROT13 cipher to alphabetic characters."""
        result = []
        for c in input_str:
            code = ord(c)
            if 65 <= code <= 90:  # Uppercase A-Z
                code = (code - 65 + 13) % 26 + 65
            elif 97 <= code <= 122:  # Lowercase a-z
                code = (code - 97 + 13) % 26 + 97
            result.append(chr(code))
        return "".join(result)


    def replace_junk(self, input_str: str) -> str:
        """Replace junk patterns with underscores."""
        for part in self.JUNK_PARTS:
            input_str = input_str.replace(part, "_")
        return input_str


    def shift_back(self, s: str, n: int) -> str:
        """Shift characters back by n positions."""
        return "".join(chr(ord(c) - n) for c in s)

    def decode_voe_string(self, encoded: str) -> Dict[str, Any]:
        try:
            step1 = self.shift_letters(encoded)
            step2 = self.replace_junk(step1).replace("_", "")
            step3 = base64.b64decode(step2).decode()
            step4 = self.shift_back(step3, 3)
            step5 = base64.b64decode(step4[::-1]).decode()
            return json.loads(step5)
        except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError) as err:
            raise ValueError(f"Failed to decode VOE string: {err}") from err

    def get_download_url(self, url):
        # Force the curl_cffi-backed Chrome impersonation for VOE: the player
        # sits behind DDoS-Guard / Cloudflare on rotating domains
        # (voe.sx → e.g. timmaybealready.com), and plain urllib gets
        # served a JS challenge instead of the player markup.
        # ``BaseClass.request`` caches by URL, so we drop the cache before
        # retrying so a stale challenge response doesn't get reused.
        self.requests.pop(url, None)
        request = self.request(url, impersonate=True)
        if request is None:
            raise CacheUrlError(f"No response from {self.title} for {url}")
        html_page = request["plain_html"].decode("utf-8")

        request_handler = RequestHandler()
        soup = request_handler.soup(request["plain_html"].decode("utf-8"))
        script = soup.find("script", type="application/json")

        if script and script.text:
            decoded = self.decode_voe_string(script.text[2:-2])
            logger.debug(f"Found script URL: {decoded.get("source")}")
            return decoded.get("source")

        VOE_PATTERNS = [re.compile(r"'hls': '([^']+)'"),
                re.compile(r'prompt\("Node",\s*"([^"]+)"'),
                re.compile(r"window\.location\.href = '([^']+)'"),
                re.compile(r"var a168c='([^']+)'"),]
        
        try:
            for VOE_PATTERN in VOE_PATTERNS:
                match = VOE_PATTERN.search(html_page)
                if match:
                    if match.group(0).startswith("window.location.href"):
                        logger.debug(f"Found window.location.href. Redirecting to new URL: {match.group(1)}")
                        return self.get_download_url(match.group(1))
                    base64_bytes = match.group(1).encode("ascii")
                    message_bytes = base64.b64decode(base64_bytes)
                    cache_url = message_bytes.decode("ascii")
                    logger.info(f"Found cache URL: {cache_url}")
                    if cache_url and cache_url.startswith("https://"):
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
        # DDoS-Guard occasionally serves a 5-second JS challenge on the
        # first request even with TLS impersonation enabled. Retrying with
        # a short backoff after a fresh handshake usually clears it.
        # Three attempts, increasing wait — the queue retries the item
        # again later anyway, so this just covers the transient case.
        last_error = None
        for attempt in range(1, 4):
            try:
                cache_url = self.get_download_url(url)
                break
            except CacheUrlError as e:
                last_error = e
                if attempt < 3:
                    backoff = 2 + attempt * 4  # 6s, 10s
                    logger.warning(
                        f"VOE attempt {attempt}/3 failed ({e}); "
                        f"retrying in {backoff}s"
                    )
                    import time as _time
                    _time.sleep(backoff)
                    self.cache_attemps = 0
                    continue
        else:
            logger.error(f"ERROR: {last_error}")
            raise CacheUrlError(last_error)

        os.makedirs(os.path.dirname(file_name), exist_ok=True)
        self._downloader = DownloaderFFmpeg(cache_url, file_name)
        self._downloader.start()

        return self._downloader