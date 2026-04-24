"""AniList GraphQL metadata client (no API key required).

Used as the primary source for the ``aniworldto`` stream. Returns the
same ``MetadataMatch`` shape as TMDb so the resolver can treat them
uniformly.
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


API_URL = "https://graphql.anilist.co"

# AniList advertises 90 req/min but degrades to 30 req/min under load.
# Keep a conservative inter-request floor so bulk refreshes don't trip 429.
_MIN_INTERVAL = 2.1  # seconds → <= 30 req/min
_MAX_RETRIES = 4

_SEARCH_QUERY = """
query ($search: String, $year: Int) {
  Page(perPage: 10) {
    media(search: $search, type: ANIME, seasonYear: $year, sort: SEARCH_MATCH) {
      id
      title { romaji english native }
      description(asHtml: false)
      startDate { year }
      averageScore
      genres
      coverImage { extraLarge large }
      bannerImage
      studios(isMain: true) { nodes { name } }
      episodes
      format
    }
  }
}
"""


class AniListProvider(MetadataProvider):
    name = "anilist"

    _gate = threading.Lock()
    _last_call: float = 0.0

    def __init__(self, *, timeout: float = 10.0) -> None:
        self._timeout = timeout

    def search(self, title: str, *, year: int | None = None,
               kind: str = "tv") -> MetadataMatch | None:
        variables: dict = {"search": title}
        if year is not None:
            variables["year"] = year
        data = self._gql(_SEARCH_QUERY, variables)

        media_list = ((data.get("data") or {}).get("Page") or {}).get("media") or []
        if not media_list:
            # Retry without year — AniList seasonYear is strict
            if year is not None:
                data = self._gql(_SEARCH_QUERY, {"search": title})
                media_list = ((data.get("data") or {}).get("Page") or {}).get("media") or []
            if not media_list:
                return None

        candidates = [self._raw_to_match(m) for m in media_list]
        candidates = [c for c in candidates if c is not None]
        best = pick_best(candidates, title, year=year)
        if best is None and candidates:
            best = candidates[0]
        return best

    # ------------------------------------------------------------------

    def _gql(self, query: str, variables: dict) -> dict:
        for attempt in range(_MAX_RETRIES):
            self._throttle()
            response = requests.post(
                API_URL,
                json={"query": query, "variables": variables},
                timeout=self._timeout,
            )
            if response.status_code == 429:
                delay = self._retry_after(response, attempt)
                if attempt == _MAX_RETRIES - 1:
                    response.raise_for_status()
                time.sleep(delay)
                continue
            response.raise_for_status()
            return response.json()
        response.raise_for_status()
        return response.json()

    @classmethod
    def _throttle(cls) -> None:
        with cls._gate:
            now = time.monotonic()
            wait = _MIN_INTERVAL - (now - cls._last_call)
            if wait > 0:
                time.sleep(wait)
            cls._last_call = time.monotonic()

    @staticmethod
    def _retry_after(response: requests.Response, attempt: int) -> float:
        header = response.headers.get("Retry-After")
        if header:
            try:
                return max(1.0, float(header))
            except ValueError:
                pass
        # Exponential backoff fallback
        return min(60.0, 2.0 ** attempt * 3.0)

    def _raw_to_match(self, raw: dict) -> MetadataMatch | None:
        titles = raw.get("title") or {}
        title = titles.get("english") or titles.get("romaji") or titles.get("native")
        if not title:
            return None

        rating = None
        score = raw.get("averageScore")
        if score is not None:
            rating = round(float(score) / 10.0, 1)  # 0–100 → 0–10

        genres = tuple(g for g in (raw.get("genres") or []) if g)
        cover = raw.get("coverImage") or {}
        poster = cover.get("extraLarge") or cover.get("large")
        banner = raw.get("bannerImage")

        start = raw.get("startDate") or {}
        year = start.get("year")

        studios = [s.get("name") for s in ((raw.get("studios") or {}).get("nodes") or []) if s.get("name")]

        return MetadataMatch(
            provider=self.name,
            id=raw["id"],
            title=title,
            overview=_strip_html(raw.get("description")),
            year=year,
            genres=genres,
            rating=rating,
            poster_url=poster,
            backdrop_url=banner,
            source_url=f"https://anilist.co/anime/{raw['id']}",
            extra={
                "format": raw.get("format"),
                "episodes": raw.get("episodes"),
                "studios": studios or None,
            },
        )


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    import re
    # AniList descriptions often contain <br>, <i>, <b>. Strip tags and
    # collapse whitespace — good enough for our plaintext storage.
    cleaned = re.sub(r"<[^>]+>", "", text)
    cleaned = re.sub(r"\s+\n", "\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()
    return cleaned or None
