"""TVmaze metadata client (no API key required).

TV-focused data source. Used as a fallback for live-action series on
streams like ``s.to`` when TMDb misses. REST API, no auth, generous rate
limits (~20 req/sec burst per IP). See https://www.tvmaze.com/api.
"""

from __future__ import annotations

import re
import threading
import time

import requests

from streamseeker.api.core.metadata.base import (
    MetadataMatch,
    MetadataProvider,
    pick_best,
)


API_URL = "https://api.tvmaze.com"
_MIN_INTERVAL = 0.1  # 10 req/s, well under the documented limit


class TvmazeProvider(MetadataProvider):
    name = "tvmaze"

    _gate = threading.Lock()
    _last_call: float = 0.0

    def __init__(self, *, timeout: float = 10.0) -> None:
        self._timeout = timeout

    def search(self, title: str, *, year: int | None = None,
               kind: str = "tv") -> MetadataMatch | None:
        # TVmaze is TV-only; skip gracefully for movie requests.
        if kind == "movie":
            return None

        self._throttle()
        response = requests.get(
            f"{API_URL}/search/shows",
            params={"q": title},
            timeout=self._timeout,
        )
        response.raise_for_status()
        results = response.json() or []

        candidates = [self._to_match(r.get("show") or {}) for r in results]
        candidates = [c for c in candidates if c is not None]
        best = pick_best(candidates, title, year=year)
        if best is None and candidates:
            best = candidates[0]
        return best

    # ------------------------------------------------------------------

    @classmethod
    def _throttle(cls) -> None:
        with cls._gate:
            now = time.monotonic()
            wait = _MIN_INTERVAL - (now - cls._last_call)
            if wait > 0:
                time.sleep(wait)
            cls._last_call = time.monotonic()

    def _to_match(self, raw: dict) -> MetadataMatch | None:
        title = raw.get("name")
        if not title:
            return None

        rating = None
        r = (raw.get("rating") or {}).get("average")
        if r is not None:
            rating = round(float(r), 1)

        genres = tuple(g for g in (raw.get("genres") or []) if g)

        image = raw.get("image") or {}
        poster = image.get("original") or image.get("medium")

        premiered = raw.get("premiered") or ""
        year = None
        m = re.match(r"^(\d{4})-", premiered)
        if m:
            year = int(m.group(1))

        summary = _strip_html(raw.get("summary"))

        return MetadataMatch(
            provider=self.name,
            id=raw.get("id"),
            title=title,
            overview=summary,
            year=year,
            genres=genres,
            rating=rating,
            poster_url=poster,
            backdrop_url=None,  # TVmaze has no dedicated backdrop field
            source_url=raw.get("url"),
            extra={
                "network": ((raw.get("network") or {}).get("name")
                            or (raw.get("webChannel") or {}).get("name")),
                "status": raw.get("status"),
                "language": raw.get("language"),
            },
        )


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"<[^>]+>", "", text)
    cleaned = re.sub(r"\s+\n", "\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()
    return cleaned or None
