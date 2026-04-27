"""Dispatch an ``enrich`` request to the right provider and cache cover images.

Stream-to-provider routing (ADRs 0007, 0008):

    aniworldto  → AniListProvider                 (anime)
    sto         → TmdbProvider (kind="tv")        (live-action series)

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
from streamseeker.api.core.metadata.base import (
    MetadataMatch,
    MetadataProvider,
)
from streamseeker.api.core.metadata.registry import (
    build_provider,
    chain_for,
    kind_for,
)

logger = Logger().instance()

# Max bytes we'll cache for a single cover. Above this, we re-encode harder.
MAX_IMAGE_BYTES = 500 * 1024
JPEG_QUALITY = 85

# poster.jpg / backdrop.jpg / logo.png — fixed names by convention (ADR 0009)
POSTER_FILENAME = "poster.jpg"
BACKDROP_FILENAME = "backdrop.jpg"
LOGO_FILENAME = "logo.png"


class MetadataResolver:
    """Walk the configured provider chain for a stream and merge every
    successful hit into the entry's ``external`` dict.

    Chain configuration lives in ``config.json`` (see ``registry.py``) —
    ADR 0007/0008 cover the default pick per stream.
    """

    def __init__(self) -> None:
        self._store = LibraryStore()
        self._provider_cache: dict[str, MetadataProvider | None] = {}

    def _get_provider(self, name: str) -> MetadataProvider | None:
        if name not in self._provider_cache:
            self._provider_cache[name] = build_provider(name)
        return self._provider_cache[name]

    # ------------------------------------------------------------------
    # Main entry points
    # ------------------------------------------------------------------

    def enrich(
        self,
        key: str,
        *,
        kind: str = KIND_LIBRARY,
        title_override: str | None = None,
        year_override: int | None = None,
        reset: bool = False,
    ) -> bool:
        """Run the provider chain for ``key``. Every provider that returns
        a match contributes its block to ``external``; the main entry
        (title, year) is taken from the **first** provider that hit.

        ``title_override`` / ``year_override`` let a caller steer the
        search when the stored title/year are ambiguous (e.g. the slug
        ``"stargate"`` should find SG-1 not the 2025 reboot, so the user
        can pass ``title_override="Stargate SG-1"``).

        ``reset=True`` drops the previously-stored ``external`` block so
        stale hits from a previous bad search don't stick around.

        Returns True if at least one provider contributed. Never raises —
        upstream failures are logged and swallowed.
        """
        entry = self._store.get(kind, key)
        if entry is None:
            return False

        stream = entry.get("stream") or ""
        slug = entry.get("slug") or ""
        title = title_override or entry.get("title") or slug.replace("-", " ").title()
        year = year_override if year_override is not None else entry.get("year")
        search_kind = kind_for(stream)

        chain = chain_for(stream)
        if not chain:
            logger.debug(f"metadata: no chain configured for stream {stream!r}")
            return False

        patched = dict(entry)
        patched.setdefault("external", {})
        existing_external = {} if reset else dict(patched.get("external") or {})

        primary_applied = False
        any_applied = False

        for provider_name in chain:
            provider = self._get_provider(provider_name)
            if provider is None:
                logger.debug(f"metadata: provider {provider_name!r} unavailable, skipping")
                continue

            try:
                match = provider.search(title, year=year, kind=search_kind)
            except requests.RequestException as exc:
                logger.warning(f"metadata lookup failed for {key} via {provider_name}: {exc}")
                continue

            if match is None:
                logger.debug(f"metadata: no match for {key} on {provider.name}")
                continue

            # Cache images (only for the primary hit — subsequent providers
            # contribute data, not artwork, to avoid churn).
            poster_file = backdrop_file = logo_file = None
            if not primary_applied:
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
            existing_external[provider.name] = block
            any_applied = True

            if not primary_applied:
                if not entry.get("year") and match.year:
                    patched["year"] = match.year
                primary_applied = True

        if not any_applied:
            return False

        patched["external"] = existing_external
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
