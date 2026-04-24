"""Detect new seasons / episodes / movies for library & favorite entries.

Each entry carries a compact content snapshot under ``content_signature``::

    {"seasons": {"1": 12, "2": 13}, "movies": 0}

A scheduled task re-scrapes the stream once per day, computes the current
signature, and stores a diff under ``pending_updates`` whenever something
changes. The extension polls ``GET /updates`` to render the "Neu" tab and
calls ``POST /updates/{key}/dismiss`` when the user has seen an entry.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from streamseeker.api.core.library.store import (
    KIND_LIBRARY,
    LibraryStore,
    _parse_key,
)
from streamseeker.api.core.logger import Logger

logger = Logger().instance()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------
# Signature + diff
# ---------------------------------------------------------------------


def build_signature(handler, stream: str, slug: str) -> dict:
    """Return a content signature for ``stream::slug`` by querying the stream.

    Shape::

        {"seasons": {"1": 12, "2": 13}, "movies": 0}

    On any scraping error, raises — the caller decides whether to log/skip.
    """
    info = handler.search(stream, slug) or {}
    types = info.get("types") or []

    seasons_map: dict[str, int] = {}
    if "staffel" in types or "serie" in types or "series" in types:
        season_numbers = list(info.get("series") or [])
        if not season_numbers:
            season_numbers = list(handler.search_seasons(stream, slug, "staffel") or [])
        for season in season_numbers:
            try:
                eps = handler.search_episodes(stream, slug, "staffel", season) or []
                seasons_map[str(season)] = len(eps)
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"episode count failed {stream}::{slug} S{season}: {exc}")
                seasons_map[str(season)] = 0

    movies_count = 0
    if "filme" in types or "movie" in types:
        if info.get("movies") is not None:
            movies_count = len(info.get("movies") or [])
        else:
            try:
                movies_count = len(handler.search_seasons(stream, slug, "filme") or [])
            except Exception:
                movies_count = 0

    return {"seasons": seasons_map, "movies": movies_count}


def diff_signatures(old: dict | None, new: dict) -> list[dict]:
    """Compute pending-update entries between two signatures.

    Each entry carries ``type``, ``detected_at``, and context fields:
      - new_season:   ``{"type":"new_season","season":4}``
      - new_episode:  ``{"type":"new_episode","season":3,"from":11,"to":12}``
      - new_movie:    ``{"type":"new_movie","count_before":2,"count_after":3}``

    If ``old`` is None (first-ever signature), nothing is reported — we only
    alert on actual *changes*, not on initial discovery.
    """
    if old is None:
        return []

    now = _now()
    updates: list[dict] = []

    old_seasons = (old.get("seasons") or {})
    new_seasons = (new.get("seasons") or {})

    for season_key in new_seasons:
        if season_key not in old_seasons:
            updates.append({
                "type": "new_season",
                "season": int(season_key) if season_key.isdigit() else season_key,
                "detected_at": now,
            })
        else:
            old_count = int(old_seasons.get(season_key) or 0)
            new_count = int(new_seasons.get(season_key) or 0)
            if new_count > old_count:
                updates.append({
                    "type": "new_episode",
                    "season": int(season_key) if season_key.isdigit() else season_key,
                    "from": old_count,
                    "to": new_count,
                    "detected_at": now,
                })

    old_movies = int(old.get("movies") or 0)
    new_movies = int(new.get("movies") or 0)
    if new_movies > old_movies:
        updates.append({
            "type": "new_movie",
            "count_before": old_movies,
            "count_after": new_movies,
            "detected_at": now,
        })

    return updates


# ---------------------------------------------------------------------
# Per-entry check
# ---------------------------------------------------------------------


@dataclass
class CheckResult:
    key: str
    kind: str
    changed: bool = False
    updates_added: int = 0
    error: str | None = None


def check_entry(handler, store: LibraryStore, kind: str, key: str) -> CheckResult:
    """Re-scrape one entry and merge new pending_updates into its JSON."""
    entry = store.get(kind, key) or {}
    if not entry:
        return CheckResult(key=key, kind=kind, error="not found")

    stream, slug = _parse_key(key)

    try:
        new_sig = build_signature(handler, stream, slug)
    except Exception as exc:  # noqa: BLE001 — treat as transient, leave prior state intact
        logger.debug(f"signature build failed {key}: {exc}")
        return CheckResult(key=key, kind=kind, error=str(exc))

    old_sig = entry.get("content_signature")
    new_updates = diff_signatures(old_sig, new_sig)

    pending = list(entry.get("pending_updates") or [])
    pending.extend(new_updates)

    patched = dict(entry)
    patched["content_signature"] = new_sig
    patched["last_checked"] = _now()
    patched["pending_updates"] = pending
    store.add(kind, patched)

    return CheckResult(
        key=key, kind=kind,
        changed=bool(new_updates),
        updates_added=len(new_updates),
    )


def dismiss_updates(store: LibraryStore, kind: str, key: str) -> bool:
    """Clear ``pending_updates`` on one entry. Returns False if it didn't exist."""
    entry = store.get(kind, key)
    if entry is None:
        return False
    patched = dict(entry)
    patched["pending_updates"] = []
    store.add(kind, patched)
    return True


# ---------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------


class UpdateChecker:
    """Background thread that runs ``check_entry`` on every library + favorite.

    Configurable via constructor:
      - ``interval_seconds``: seconds between scans (default 86400 = 24 h)
      - ``initial_delay``: seconds before the first run (default 900 = 15 min)
      - ``between_entries``: throttle per entry to avoid hammering the site
    """

    def __init__(
        self,
        handler,
        *,
        interval_seconds: int = 24 * 60 * 60,
        initial_delay: int = 15 * 60,
        between_entries: float = 2.0,
    ) -> None:
        self._handler = handler
        self._interval = interval_seconds
        self._initial_delay = initial_delay
        self._between = between_entries
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ss-update-checker")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        if self._stop.wait(self._initial_delay):
            return
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"update check cycle failed: {exc}")
            if self._stop.wait(self._interval):
                return

    def run_once(self) -> list[CheckResult]:
        """Check every library entry once (favorites live in the library too
        now — flag-based). Called by the scheduler and exposed for tests."""
        store = LibraryStore()
        results: list[CheckResult] = []
        for row in store.list(KIND_LIBRARY):
            key = row.get("key")
            if not key:
                continue
            res = check_entry(self._handler, store, KIND_LIBRARY, key)
            results.append(res)
            if self._between > 0 and not self._stop.is_set():
                time.sleep(self._between)
        return results


# ---------------------------------------------------------------------
# Collect pending for the API
# ---------------------------------------------------------------------


def collect_pending(store: LibraryStore) -> list[dict]:
    """Return every library entry that has pending_updates, including its
    ``favorite`` flag so the popup can prioritise ★-marked shows."""
    rows: list[dict] = []
    for indexed in store.list(KIND_LIBRARY):
        key = indexed.get("key")
        if not key:
            continue
        entry = store.get(KIND_LIBRARY, key) or {}
        pending = entry.get("pending_updates") or []
        if not pending:
            continue
        rows.append({
            "key": key,
            "stream": entry.get("stream"),
            "slug": entry.get("slug"),
            "title": entry.get("title"),
            "favorite": bool(entry.get("favorite")),
            "pending_updates": pending,
            "last_checked": entry.get("last_checked"),
        })
    return rows
