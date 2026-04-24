"""Dispatch an ``enrich`` request to the right provider and cache cover images.

Stream-to-provider routing (ADRs 0007, 0008):

    aniworldto  → AniListProvider                 (anime)
    sto         → TmdbProvider (kind="tv")        (live-action series)
    megakinotax → TmdbProvider (kind="movie")     (movies)

Enrichment is additive: it writes under ``external.<provider>`` of the
Library entry, downloads poster/backdrop into the series asset folder, and
leaves every other field untouched.
"""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

from streamseeker import paths
from streamseeker.api.core.library import LibraryStore
from streamseeker.api.core.library.store import KIND_FAVORITES, KIND_LIBRARY
from streamseeker.api.core.logger import Logger
from streamseeker.api.core.metadata.anilist import AniListProvider
from streamseeker.api.core.metadata.base import (
    MetadataMatch,
    MetadataProvider,
    MetadataUnavailableError,
)
from streamseeker.api.core.metadata.tmdb import TmdbProvider

logger = Logger().instance()

# Max bytes we'll cache for a single cover. Above this, we re-encode harder.
MAX_IMAGE_BYTES = 500 * 1024
JPEG_QUALITY = 85

# poster.jpg / backdrop.jpg / logo.png — fixed names by convention (ADR 0009)
POSTER_FILENAME = "poster.jpg"
BACKDROP_FILENAME = "backdrop.jpg"
LOGO_FILENAME = "logo.png"


class MetadataResolver:
    """Decide which provider to call and apply its match to the Library."""

    def __init__(self) -> None:
        # Build providers lazily — missing TMDb key must not break AniList.
        self._providers_by_stream: dict[str, tuple[MetadataProvider, str]] = {}
        self._store = LibraryStore()

    # ------------------------------------------------------------------
    # Provider choice
    # ------------------------------------------------------------------

    def provider_for(self, stream: str) -> tuple[MetadataProvider | None, str]:
        """Return (provider, kind) for a stream slug. Caches instances."""
        if stream in self._providers_by_stream:
            return self._providers_by_stream[stream]

        provider: MetadataProvider | None
        kind: str
        if stream == "aniworldto":
            provider = AniListProvider()
            kind = "tv"
        elif stream == "sto":
            try:
                provider = TmdbProvider()
            except MetadataUnavailableError:
                provider = None
            kind = "tv"
        elif stream == "megakinotax":
            try:
                provider = TmdbProvider()
            except MetadataUnavailableError:
                provider = None
            kind = "movie"
        else:
            provider = None
            kind = "tv"

        self._providers_by_stream[stream] = (provider, kind)
        return provider, kind

    # ------------------------------------------------------------------
    # Main entry points
    # ------------------------------------------------------------------

    def enrich(self, key: str, *, kind: str = KIND_LIBRARY) -> bool:
        """Look up metadata for a Library- or Favorites-Eintrag and merge it.

        Returns True if any enrichment was applied. Never raises — all
        upstream failures are logged and swallowed so store writes are
        best-effort.
        """
        entry = self._store.get(kind, key)
        if entry is None:
            return False

        stream = entry.get("stream") or ""
        slug = entry.get("slug") or ""
        title = entry.get("title") or slug.replace("-", " ").title()
        year = entry.get("year")

        provider, search_kind = self.provider_for(stream)
        if provider is None:
            logger.debug(f"metadata: no provider for stream {stream!r}")
            return False

        try:
            match = provider.search(title, year=year, kind=search_kind)
        except requests.RequestException as exc:
            logger.warning(f"metadata lookup failed for {key}: {exc}")
            return False

        if match is None:
            logger.debug(f"metadata: no match for {key} on {provider.name}")
            return False

        # Cache images and build the external block
        asset_dir = paths.series_dir(kind, stream, slug)
        poster_file = self._cache_image(match.poster_url, asset_dir, POSTER_FILENAME)
        backdrop_file = self._cache_image(match.backdrop_url, asset_dir, BACKDROP_FILENAME)
        logo_file = self._cache_image(match.logo_url, asset_dir, LOGO_FILENAME, allow_png=True)

        block = match.to_external_block(
            poster_file=poster_file,
            backdrop_file=backdrop_file,
            logo_file=logo_file,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

        # Merge via add() so we inherit existing downloaded-episode lists
        patched = dict(entry)
        patched.setdefault("external", {})
        patched["external"] = {**entry.get("external", {}), provider.name: block}
        # Also pull in year/title from the match if the entry lacked them
        if not entry.get("year") and match.year:
            patched["year"] = match.year
        self._store.add(kind, patched)
        return True

    # ------------------------------------------------------------------
    # Image handling
    # ------------------------------------------------------------------

    def _cache_image(self, url: str | None, asset_dir: Path, filename: str,
                     *, allow_png: bool = False) -> str | None:
        """Download ``url`` into ``asset_dir/filename`` (JPEG re-encoded)."""
        if not url:
            return None

        try:
            response = requests.get(url, timeout=15.0, stream=True)
            response.raise_for_status()
            raw = response.content
        except requests.RequestException as exc:
            logger.warning(f"cover download failed: {url} — {exc}")
            return None

        asset_dir.mkdir(parents=True, exist_ok=True)
        target = asset_dir / filename
        tmp = target.with_suffix(target.suffix + ".tmp")

        try:
            from PIL import Image  # local import keeps import-time cheap

            buf = io.BytesIO(raw)
            img = Image.open(buf)
            if filename.endswith(".png") and allow_png:
                img.save(tmp, format="PNG", optimize=True)
            else:
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(tmp, format="JPEG", quality=JPEG_QUALITY, optimize=True)
                # One more pass if still too fat
                if tmp.stat().st_size > MAX_IMAGE_BYTES:
                    img.save(tmp, format="JPEG", quality=70, optimize=True)
        except Exception as exc:
            logger.warning(f"image re-encode failed ({url}): {exc}")
            if tmp.exists():
                tmp.unlink()
            return None

        os.replace(tmp, target)
        return filename
