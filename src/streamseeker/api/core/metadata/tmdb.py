"""The Movie Database (TMDb) v3 metadata client.

Key is loaded from ``~/.streamseeker/config.credentials.json`` under
``tmdb_api_key``. Missing keys raise ``MetadataUnavailableError`` so the
resolver can skip cleanly.

Endpoints used:
- ``GET /search/tv`` and ``GET /search/movie`` — initial match
- ``GET /tv/{id}`` / ``GET /movie/{id}`` — full details + certification
- ``GET /configuration`` cached to build image URLs (``secure_base_url``)
"""

from __future__ import annotations

from typing import Literal

import requests

from streamseeker import paths
from streamseeker.api.core.metadata.base import (
    MetadataMatch,
    MetadataProvider,
    MetadataUnavailableError,
    pick_best,
)


API_BASE = "https://api.themoviedb.org/3"
DEFAULT_POSTER_SIZE = "w500"
DEFAULT_BACKDROP_SIZE = "w1280"


class TmdbProvider(MetadataProvider):
    name = "tmdb"

    # Primary language — English (universal fallback). Additional languages
    # are fetched as translations and stored under
    # ``external.tmdb.translations.{xx}`` for the popup to overlay at render
    # time. Maps the i18n code we use elsewhere (``de`` / ``en``) to the
    # IETF tag TMDb expects.
    PRIMARY_LANGUAGE = "en-US"
    TRANSLATION_LANGUAGES = {"de": "de-DE"}

    def __init__(self, api_key: str | None = None, *,
                 language: str | None = None, timeout: float = 10.0) -> None:
        self._api_key = api_key or paths.load_credentials().get("tmdb_api_key")
        if not self._api_key:
            raise MetadataUnavailableError(
                "TMDb API key missing — set 'tmdb_api_key' in "
                "~/.streamseeker/config.credentials.json"
            )
        # ``language`` is kept for backward compat but ignored — primary is
        # always English so it can serve as the universal fallback. Use the
        # ``TRANSLATION_LANGUAGES`` mapping to add more locales.
        self._language = language or self.PRIMARY_LANGUAGE
        self._timeout = timeout
        self._image_base: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, title: str, *, year: int | None = None,
               kind: Literal["tv", "movie"] = "tv") -> MetadataMatch | None:
        endpoint = "/search/tv" if kind == "tv" else "/search/movie"
        params: dict = {"query": title, "include_adult": "false"}
        if year is not None:
            params["first_air_date_year" if kind == "tv" else "year"] = year

        data = self._get(endpoint, params=params)
        results = data.get("results") or []
        if not results:
            return None

        candidates = [self._raw_to_match(r, kind) for r in results]
        candidates = [c for c in candidates if c is not None]
        best = pick_best(candidates, title, year=year)
        # TMDb usually returns relevance-sorted results; if our scoring found
        # nothing noteworthy, still fall back to the first result so a user
        # with an exact title always gets *something* instead of None.
        if best is None and candidates:
            best = candidates[0]
        if best is None:
            return None

        # Enrich with per-title details (certification, genres) — one extra GET
        detailed = self.details(best.id, kind=kind)
        return detailed or best

    def details(self, match_id: int | str, *,
                kind: Literal["tv", "movie"] = "tv") -> MetadataMatch | None:
        endpoint = f"/tv/{match_id}" if kind == "tv" else f"/movie/{match_id}"
        extras = "content_ratings" if kind == "tv" else "release_dates"
        data = self._get(endpoint, params={"append_to_response": extras})
        if not data:
            return None
        match = self._detailed_to_match(data, kind)
        # Fetch each configured translation. Cheap (one extra GET per
        # language without ``append_to_response``) — failures are swallowed
        # so a missing translation never breaks enrichment.
        translations: dict[str, dict] = {}
        for code, locale in self.TRANSLATION_LANGUAGES.items():
            try:
                translations[code] = self._fetch_translation(match_id, kind, locale)
            except requests.RequestException:
                continue
        if any(translations.values()):
            match = _with_translations(match, translations)
        return match

    def _fetch_translation(self, match_id: int | str, kind: str, locale: str) -> dict:
        """Return a small dict ``{title, overview, genres, tagline}`` in ``locale``.

        Empty fields are dropped so :func:`localize_block` doesn't overlay
        nothing-strings on top of the primary language.
        """
        endpoint = f"/tv/{match_id}" if kind == "tv" else f"/movie/{match_id}"
        data = self._get_raw(endpoint, params={"language": locale})
        if not data:
            return {}
        title = data.get("name") if kind == "tv" else data.get("title")
        return {
            "title": title or None,
            "overview": data.get("overview") or None,
            "genres": [g.get("name") for g in (data.get("genres") or []) if g.get("name")] or None,
            "tagline": data.get("tagline") or None,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get(self, endpoint: str, *, params: dict | None = None) -> dict:
        # Default language is the provider's primary; callers can override
        # by passing ``language`` in ``params`` (used for translations).
        p = {"api_key": self._api_key, "language": self._language}
        if params:
            p.update(params)
        response = requests.get(f"{API_BASE}{endpoint}", params=p, timeout=self._timeout)
        if response.status_code == 404:
            return {}
        response.raise_for_status()
        return response.json()

    def _get_raw(self, endpoint: str, *, params: dict | None = None) -> dict:
        """Like ``_get`` but does NOT inject the primary language — caller
        must specify ``language`` in ``params`` (for translation calls)."""
        p = {"api_key": self._api_key}
        if params:
            p.update(params)
        response = requests.get(f"{API_BASE}{endpoint}", params=p, timeout=self._timeout)
        if response.status_code == 404:
            return {}
        response.raise_for_status()
        return response.json()

    def _image_base_url(self) -> str:
        if self._image_base:
            return self._image_base
        cfg = self._get("/configuration")
        images = cfg.get("images", {}) or {}
        self._image_base = images.get("secure_base_url") or "https://image.tmdb.org/t/p/"
        return self._image_base

    def _raw_to_match(self, raw: dict, kind: str) -> MetadataMatch | None:
        title = raw.get("name") if kind == "tv" else raw.get("title")
        if not title:
            return None
        year = _year(raw.get("first_air_date") if kind == "tv" else raw.get("release_date"))
        poster = self._image_url(raw.get("poster_path"), DEFAULT_POSTER_SIZE)
        backdrop = self._image_url(raw.get("backdrop_path"), DEFAULT_BACKDROP_SIZE)
        return MetadataMatch(
            provider=self.name,
            id=raw["id"],
            title=title,
            overview=raw.get("overview") or None,
            year=year,
            rating=(raw.get("vote_average") or None) and round(float(raw["vote_average"]), 1),
            poster_url=poster,
            backdrop_url=backdrop,
            source_url=f"https://www.themoviedb.org/{'tv' if kind == 'tv' else 'movie'}/{raw['id']}",
        )

    def _detailed_to_match(self, raw: dict, kind: str) -> MetadataMatch:
        title = raw.get("name") if kind == "tv" else raw.get("title")
        year = _year(raw.get("first_air_date") if kind == "tv" else raw.get("release_date"))
        genres = tuple(g.get("name") for g in raw.get("genres", []) if g.get("name"))
        poster = self._image_url(raw.get("poster_path"), DEFAULT_POSTER_SIZE)
        backdrop = self._image_url(raw.get("backdrop_path"), DEFAULT_BACKDROP_SIZE)
        fsk = _pick_certification(raw, kind)

        return MetadataMatch(
            provider=self.name,
            id=raw["id"],
            title=title,
            overview=raw.get("overview") or None,
            year=year,
            genres=genres,
            rating=(raw.get("vote_average") or None) and round(float(raw["vote_average"]), 1),
            fsk=fsk,
            poster_url=poster,
            backdrop_url=backdrop,
            source_url=f"https://www.themoviedb.org/{'tv' if kind == 'tv' else 'movie'}/{raw['id']}",
        )

    def _image_url(self, path: str | None, size: str) -> str | None:
        if not path:
            return None
        base = self._image_base_url().rstrip("/")
        return f"{base}/{size}{path}"


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def _with_translations(match: MetadataMatch, translations: dict[str, dict]) -> MetadataMatch:
    """Return a copy of ``match`` with the given translations attached.

    Drops translation entries that are entirely empty so the stored block
    stays compact.
    """
    cleaned = {
        lang: {k: v for k, v in tr.items() if v not in (None, "", [], {})}
        for lang, tr in translations.items()
    }
    cleaned = {lang: tr for lang, tr in cleaned.items() if tr}
    if not cleaned:
        return match
    from dataclasses import replace
    return replace(match, translations=cleaned)


def _year(date_str: str | None) -> int | None:
    if not date_str:
        return None
    try:
        return int(date_str[:4])
    except (TypeError, ValueError):
        return None


_FSK_PRIORITY = {"de": 0, "at": 1, "ch": 2, "us": 3, "gb": 4}  # lower = preferred


def _pick_certification(raw: dict, kind: str) -> str | None:
    """Pick a human-readable age rating, preferring German-speaking countries."""
    if kind == "tv":
        entries = raw.get("content_ratings", {}).get("results", []) or []
        candidates = [
            (e.get("iso_3166_1", "").lower(), e.get("rating"))
            for e in entries
            if e.get("rating")
        ]
    else:
        entries = raw.get("release_dates", {}).get("results", []) or []
        candidates = []
        for e in entries:
            country = (e.get("iso_3166_1") or "").lower()
            for rd in e.get("release_dates", []) or []:
                cert = rd.get("certification")
                if cert:
                    candidates.append((country, cert))
                    break

    if not candidates:
        return None
    candidates.sort(key=lambda c: _FSK_PRIORITY.get(c[0], 99))
    country, cert = candidates[0]
    if country in ("de", "at", "ch"):
        return f"FSK {cert}" if cert.isdigit() else cert
    return cert
