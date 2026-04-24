"""Jikan (MyAnimeList) metadata client — keyfree anime fallback.

Used alongside AniList for ``aniworldto`` when AniList misses (rare obscure
anime, differently-romanized titles). Rate limits are strict: 3 req/sec
and 60 req/min. We throttle conservatively. See https://jikan.moe.
"""

from __future__ import annotations

import threading
import time

import requests

from streamseeker.api.core.metadata.base import (
    MetadataMatch,
    MetadataProvider,
    pick_best,
)


API_URL = "https://api.jikan.moe/v4"
_MIN_INTERVAL = 0.35  # ~3 req/s upper limit
_MAX_RETRIES = 3


class JikanProvider(MetadataProvider):
    name = "jikan"

    _gate = threading.Lock()
    _last_call: float = 0.0

    def __init__(self, *, timeout: float = 10.0) -> None:
        self._timeout = timeout

    def search(self, title: str, *, year: int | None = None,
               kind: str = "tv") -> MetadataMatch | None:
        for attempt in range(_MAX_RETRIES):
            self._throttle()
            response = requests.get(
                f"{API_URL}/anime",
                params={"q": title, "limit": 10, "order_by": "popularity"},
                timeout=self._timeout,
            )
            if response.status_code == 429:
                if attempt == _MAX_RETRIES - 1:
                    response.raise_for_status()
                time.sleep(min(30.0, 2.0 ** attempt * 2.0))
                continue
            response.raise_for_status()
            break

        data = response.json() or {}
        raw_list = data.get("data") or []
        candidates = [self._to_match(r) for r in raw_list]
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
        titles = raw.get("titles") or []
        title = None
        for t in titles:
            if t.get("type") == "English":
                title = t.get("title"); break
        if not title:
            title = raw.get("title_english") or raw.get("title")
        if not title:
            return None

        score = raw.get("score")
        rating = round(float(score), 1) if score is not None else None

        genres = tuple(
            g.get("name") for g in (raw.get("genres") or []) if g.get("name")
        )

        images = raw.get("images") or {}
        jpg = images.get("jpg") or {}
        poster = jpg.get("large_image_url") or jpg.get("image_url")

        aired = raw.get("aired") or {}
        year = None
        from_date = aired.get("from") or ""
        if len(from_date) >= 4 and from_date[:4].isdigit():
            year = int(from_date[:4])

        studios = [s.get("name") for s in (raw.get("studios") or []) if s.get("name")]

        return MetadataMatch(
            provider=self.name,
            id=raw.get("mal_id"),
            title=title,
            overview=raw.get("synopsis"),
            year=year,
            genres=genres,
            rating=rating,
            poster_url=poster,
            backdrop_url=None,
            source_url=raw.get("url"),
            extra={
                "type": raw.get("type"),
                "episodes": raw.get("episodes"),
                "status": raw.get("status"),
                "studios": studios or None,
            },
        )
