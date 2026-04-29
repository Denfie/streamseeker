import re
import time
import random

from urllib.request import urlopen, Request
from urllib.error import URLError
from urllib.parse import urlparse, urlencode

from bs4 import BeautifulSoup

from streamseeker.api.core.logger import Logger
logger = Logger().instance()

# curl_cffi gives us a libcurl-impersonate-backed Session that mimics
# Chrome's TLS / HTTP-2 fingerprint. Hosts behind DDoS-Guard or
# Cloudflare (e.g. the rotating VOE redirect domains like
# ``timmaybealready.com``) tend to let those through where plain urllib
# gets challenged. No browser process is spawned — it's still just an
# HTTP client, so the daemon can run headless. We import lazily and
# fall back to urllib if the native binary isn't installed on the host.
try:
    from curl_cffi.requests import Session as _CurlSession  # type: ignore
    _HAS_CURL_CFFI = True
except Exception:  # noqa: BLE001 — any import error falls back cleanly
    _CurlSession = None  # type: ignore
    _HAS_CURL_CFFI = False


class _CurlResponseAdapter:
    """Make a ``curl_cffi`` response quack like ``urllib.urlopen``.

    Existing call sites do ``response.read()``, ``response.url`` and
    ``response.headers`` — urllib's interface. Wrapping the curl_cffi
    Response keeps the rest of the codebase unchanged.
    """

    def __init__(self, resp):
        self._resp = resp
        self._content = resp.content
        self._consumed = False

    def read(self):
        # urllib's response.read() returns bytes once and is exhausted
        # afterwards; mirror that for parity with retrying / caching code
        # paths in BaseClass.request.
        if self._consumed:
            return b""
        self._consumed = True
        return self._content

    @property
    def url(self) -> str:
        return str(self._resp.url)

    @property
    def headers(self):
        # urllib headers behave like a Mapping; curl_cffi gives us
        # ``response.headers`` already mapping-shaped.
        return self._resp.headers

    @property
    def status(self) -> int:
        return int(self._resp.status_code)

class RequestHandler:
    # Hosts where DDoS-Guard / Cloudflare / similar anti-bot services
    # routinely sit in front of the player. For these we always use
    # curl_cffi when available so the TLS fingerprint matches Chrome.
    # Other hosts fall through to plain urllib to avoid loading the
    # native libcurl-impersonate binary for every harmless scrape.
    _IMPERSONATE_HOSTS = {
        "voe.sx", "voe-network.com", "voe-cdn.com", "voe-network.net",
        # VOE rotates its real player domain via a JS redirect from
        # voe.sx → <random>.com. We can't enumerate them all up front,
        # so the runtime check below also impersonates whenever the
        # caller explicitly opted in via ``impersonate=True``.
    }

    def __init__(self):
        self._user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.81 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.97 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.96 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.81 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.97 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.96 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.81 Safari/537.36",
        ]

    def get_header(self, url):
        parsed_url = urlparse(url)
        referer = f"{parsed_url.scheme}://{parsed_url.netloc}"

        headers = {
            "User-Agent": random.choice(self._user_agents),
            "Referer": referer
        }
        return headers
    
    def _should_impersonate(self, url: str, force: bool) -> bool:
        if force:
            return _HAS_CURL_CFFI
        if not _HAS_CURL_CFFI:
            return False
        try:
            host = urlparse(url).hostname or ""
        except Exception:  # noqa: BLE001
            return False
        return any(host == h or host.endswith("." + h) for h in self._IMPERSONATE_HOSTS)

    def get(self, url, headers=None, impersonate=False) -> urlopen:
        header_keys = headers.keys() if headers is not None else []

        _headers = self.get_header(url).copy()
        _headers_keys = _headers.keys()

        for key in header_keys:
            if key in _headers_keys:
                _headers[key] = headers[key]

        if self._should_impersonate(url, impersonate):
            try:
                with _CurlSession() as session:
                    resp = session.get(
                        url,
                        headers=_headers,
                        timeout=100,
                        impersonate="chrome120",
                        allow_redirects=True,
                    )
                    return _CurlResponseAdapter(resp)
            except Exception as e:  # noqa: BLE001 — fall through to urllib
                logger.warning(f"curl_cffi GET failed for {url}: {e} — retrying with urllib")

        request = Request(url, headers=_headers)
        try:
            response = urlopen(request, timeout=100)
            return response
        except URLError as e:
            logger.error(f"{url}: {_headers}")
            logger.error(f"Error while trying to get the url: {url}")
            logger.error(f"Error: {e}")
            return None
        
    def get_soup(self, url, headers=None):
        response = self.get(url, headers)
        if response is None:
            return None
        
        return self.soup(response)
    
    def soup(self, html):
        if html is None:
            return None
        
        return BeautifulSoup(html, features="html.parser")
    
    def post(self, url, data, headers=None):
        header_keys = headers.keys() if headers is not None else []

        _headers = self.get_header(url).copy()
        _headers_keys = _headers.keys()

        for key in header_keys:
            if key in _headers_keys:
                _headers[key] = headers[key]

        data = urlencode(data).encode()
        request = Request(url, headers=_headers, data=data)
        try:
            response = urlopen(request, timeout=100)
            return response
        except URLError as e:
            logger.error(f"{url}: {_headers}")
            logger.error(f"Error while trying to post the url: {url}")
            logger.error(f"Error: {e}")
            return None