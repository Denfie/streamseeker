"""FastAPI application factory for the StreamSeeker daemon."""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from streamseeker import paths
from streamseeker.api.core.downloader.manager import DownloadManager
from streamseeker.api.core.library import LibraryStore
from streamseeker.api.core.library.store import KIND_FAVORITES, KIND_LIBRARY
from streamseeker.api.core.logger import Logger
from streamseeker.api.core.metadata.resolver import MetadataResolver
from streamseeker.utils._compat import get_version

logger = Logger().instance()


def _safe_enrich(key: str, kind: str) -> None:
    try:
        MetadataResolver().enrich(key, kind=kind)
    except Exception as exc:  # noqa: BLE001 — background task must never surface
        logger.warning(f"background enrich failed for {key} ({kind}): {exc}")


def _infer_scope(req: "QueueItemRequest") -> str:
    """Back-compat scope inference for clients that don't send ``scope``."""
    if req.type == "filme":
        return "single"
    if req.season > 0 and req.episode > 0:
        return "single"
    if req.season > 0 and req.episode == 0:
        return "season"
    return "all"


# ---------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------


class FavoriteRequest(BaseModel):
    stream: str = Field(min_length=1)
    slug: str = Field(min_length=1)


class QueueItemRequest(BaseModel):
    stream: str
    slug: str
    scope: Optional[str] = None  # "single" | "season" | "from" | "all"
    type: str = "staffel"
    season: int = 0
    episode: int = 0
    language: str = "german"
    preferred_provider: Optional[str] = None
    file_name: Optional[str] = None


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _format_key(stream: str, slug: str) -> str:
    return f"{stream}::{slug}"


def _build_status() -> dict:
    manager = DownloadManager()
    return {
        "summary": manager.queue_summary(),
        "progress": manager.get_progress(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _serve_asset(key: str, filename: str, kind: str = KIND_LIBRARY):
    """Return the asset file from ``<kind>/<stream>/<slug>/<filename>``.

    If the primary kind doesn't carry the asset, fall back to the other kind
    so promote/demote leaves covers usable from either side.
    Returns 404 if the key is invalid or the file doesn't exist.
    """
    if "::" not in key:
        raise HTTPException(status_code=404, detail="invalid key")
    stream, slug = key.split("::", 1)
    asset = paths.series_dir(kind, stream, slug) / filename
    if not asset.is_file():
        fallback_kind = KIND_FAVORITES if kind == KIND_LIBRARY else KIND_LIBRARY
        asset = paths.series_dir(fallback_kind, stream, slug) / filename
        if not asset.is_file():
            raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(asset)


def _library_state(stream: str, slug: str) -> dict:
    """Compact status map used by the Chrome extension's content script.

    Each season carries aggregates (``total/downloaded/queued/failed``) plus
    an ``episodes`` map: ``{"<episode_number>": "downloaded"|"queued"|"failed"}``
    so the extension can colour individual episode links without another
    round-trip.
    """
    store = LibraryStore()
    key = _format_key(stream, slug)

    lib_entry = store.get(KIND_LIBRARY, key)
    favorite = bool(lib_entry and lib_entry.get("favorite"))

    manager = DownloadManager()
    queue = manager.get_queue()

    def _empty_season() -> dict:
        return {"total": 0, "downloaded": 0, "queued": 0, "skipped": 0, "failed": 0, "episodes": {}}

    season_states: dict[str, dict] = {}

    if lib_entry:
        for season_key, season_data in (lib_entry.get("seasons") or {}).items():
            bucket = season_states.setdefault(season_key, _empty_season())
            bucket["total"] = season_data.get("episode_count", 0) or 0
            for ep in season_data.get("downloaded", []):
                bucket["episodes"][str(ep)] = "downloaded"
            bucket["downloaded"] = sum(
                1 for v in bucket["episodes"].values() if v == "downloaded"
            )

    for item in queue:
        if item.get("stream_name") != stream or item.get("name") != slug:
            continue
        season = str(item.get("season", 0))
        bucket = season_states.setdefault(season, _empty_season())
        status = item.get("status", "pending")
        episode = item.get("episode")
        ep_key = str(episode) if episode else None

        if status == "downloading":
            bucket["queued"] += 1
            if ep_key and bucket["episodes"].get(ep_key) != "downloaded":
                bucket["episodes"][ep_key] = "queued"
        elif status in ("pending", "paused", "skipped"):
            bucket["skipped"] += 1
            if ep_key and bucket["episodes"].get(ep_key) not in ("downloaded", "queued"):
                bucket["episodes"][ep_key] = "skipped"
        elif status == "failed":
            bucket["failed"] += 1
            if ep_key and bucket["episodes"].get(ep_key) != "downloaded":
                bucket["episodes"][ep_key] = "failed"

    return {
        "key": key,
        "favorite": favorite,
        "library": lib_entry is not None,
        "seasons": season_states,
    }


# ---------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(
        title="StreamSeeker Daemon",
        version=get_version(),
        docs_url="/docs",
    )

    # CORS — open for localhost, browser-extension origins AND the stream
    # host pages. In Manifest V3 a content-script's fetch() uses the host
    # page's origin (e.g. https://aniworld.to), not chrome-extension://*.
    # Safe because the daemon is bound to 127.0.0.1 and never listens on a
    # public interface.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=(
            r"^("
            r"chrome-extension://.*"
            r"|moz-extension://.*"
            r"|http://127\.0\.0\.1(:\d+)?"
            r"|http://localhost(:\d+)?"
            r"|https://(aniworld\.to|s\.to|megakino\.tax)"
            r")$"
        ),
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def _migrate_favorites_on_startup() -> None:
        try:
            moved = LibraryStore().migrate_favorites_into_library()
            if moved:
                logger.info(f"merged {moved} favorite(s) into the library")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"favorites migration failed: {exc}")

    @app.on_event("startup")
    def _start_queue_processor() -> None:
        from streamseeker.api.core.downloader.processor import QueueProcessor
        from streamseeker.api.handler import StreamseekerHandler
        try:
            handler = StreamseekerHandler()
            processor = QueueProcessor()
            if not processor.is_running():
                processor.start(config=handler.config)
                logger.info("queue processor started")
        except Exception as exc:  # noqa: BLE001 — startup best-effort
            logger.warning(f"queue processor failed to start: {exc}")

    @app.on_event("shutdown")
    def _stop_queue_processor() -> None:
        from streamseeker.api.core.downloader.processor import QueueProcessor
        try:
            QueueProcessor().stop()
        except Exception:  # noqa: BLE001
            pass

    @app.on_event("startup")
    def _start_update_checker() -> None:
        from streamseeker.api.core.library.updates import UpdateChecker
        from streamseeker.api.handler import StreamseekerHandler
        try:
            app.state.update_checker = UpdateChecker(StreamseekerHandler())
            app.state.update_checker.start()
            logger.info("update checker started")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"update checker failed to start: {exc}")

    @app.on_event("shutdown")
    def _stop_update_checker() -> None:
        checker = getattr(app.state, "update_checker", None)
        if checker:
            try:
                checker.stop()
            except Exception:  # noqa: BLE001
                pass

    # -----------------------------------------------------------------
    # Meta
    # -----------------------------------------------------------------

    @app.get("/version")
    def version() -> dict:
        return {"cli": get_version()}

    @app.get("/status")
    def status() -> dict:
        return _build_status()

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        return _DASHBOARD_HTML

    # -----------------------------------------------------------------
    # Series structure (scope picker in the extension modal)
    # -----------------------------------------------------------------

    @app.get("/series/{stream}/{slug}/structure")
    def series_structure(stream: str, slug: str) -> dict:
        """Return seasons + available languages/providers for the scope
        picker in the browser extension's modal. Mirrors what the CLI
        wizard collects interactively."""
        from streamseeker.api.handler import StreamseekerHandler
        handler = StreamseekerHandler()
        try:
            info = handler.search(stream, slug) or {}
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"search failed: {exc}"
            ) from exc

        types = list(info.get("types") or [])
        # ``search()`` already returns series/movies lists for aniworld+sto;
        # fall back to search_seasons() for streams that don't expose them
        # directly (e.g. megakinotax).
        seasons = list(info.get("series") or [])
        movies_list = list(info.get("movies") or [])
        if not seasons and ("staffel" in types or "serie" in types or "series" in types):
            try:
                seasons = list(handler.search_seasons(stream, slug, "staffel") or [])
            except Exception as exc:
                logger.warning(f"search_seasons failed for {stream}::{slug}: {exc}")
        if not movies_list and ("filme" in types or "movie" in types):
            try:
                movies_list = list(handler.search_seasons(stream, slug, "filme") or [])
            except Exception as exc:
                logger.warning(f"movies count failed for {stream}::{slug}: {exc}")

        result: dict = {
            "types": types,
            "seasons": seasons,
            "movies": len(movies_list),
            "languages": {},
            "providers": {},
        }

        # Languages/providers — fetched on the first available (season, episode)
        # so the user sees what's actually offered by the site.
        detail_type = "staffel" if result["seasons"] else ("filme" if result["movies"] else "staffel")
        detail_season = result["seasons"][0] if result["seasons"] else 1
        try:
            details = handler.search_details(stream, slug, detail_type, detail_season, 1) or {}
            result["languages"] = details.get("languages") or {}
            result["providers"] = details.get("providers") or {}
        except Exception as exc:
            logger.warning(f"search_details failed for {stream}::{slug}: {exc}")

        return result

    @app.get("/series/{stream}/{slug}/episodes")
    def series_episodes(stream: str, slug: str, season: int, type: str = "staffel") -> dict:
        from streamseeker.api.handler import StreamseekerHandler
        try:
            eps = StreamseekerHandler().search_episodes(stream, slug, type, season) or []
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"episodes lookup failed: {exc}"
            ) from exc
        return {"season": season, "episodes": list(eps)}

    # -----------------------------------------------------------------
    # Queue
    # -----------------------------------------------------------------

    @app.get("/queue")
    def queue_list() -> list[dict]:
        return DownloadManager().get_queue()

    @app.post("/queue", status_code=201)
    def queue_add(req: QueueItemRequest) -> dict:
        """Enqueue episodes/seasons via the handler so queue items carry
        the real destination path, provider and language — otherwise the
        QueueProcessor has nothing usable to download."""
        from streamseeker.api.handler import StreamseekerHandler

        handler = StreamseekerHandler()
        provider = req.preferred_provider or handler.config.get("preferred_provider") or "voe"
        language = req.language or "german"
        scope = (req.scope or _infer_scope(req)).lower()

        try:
            if req.type == "filme" or scope == "single":
                count = handler.enqueue_single(
                    req.stream, provider, req.slug, language, req.type,
                    season=req.season, episode=req.episode,
                )
            elif scope == "season":
                # Only this season, all episodes
                count = handler.enqueue_all(
                    req.stream, provider, req.slug, language, req.type,
                    season=req.season, episode=0,
                    seasons_list=[req.season] if req.season else None,
                )
            elif scope == "from":
                # From S/E onwards
                count = handler.enqueue_all(
                    req.stream, provider, req.slug, language, req.type,
                    season=req.season, episode=req.episode,
                )
            else:  # "all"
                count = handler.enqueue_all(
                    req.stream, provider, req.slug, language, req.type,
                )
        except Exception as exc:  # noqa: BLE001 — surface as HTTP 500-style reply
            logger.exception(f"enqueue failed for {req.stream}::{req.slug}: {exc}")
            raise HTTPException(status_code=500, detail=f"enqueue failed: {exc}") from exc

        return {"enqueued": True, "count": count}

    def _require_queue_item(file_name: str) -> dict:
        item = DownloadManager()._find_in_queue(file_name)
        if item is None:
            raise HTTPException(status_code=404, detail=f"not in queue: {file_name}")
        return item

    @app.post("/queue/{file_name:path}/pause")
    def queue_pause(file_name: str) -> dict:
        _require_queue_item(file_name)
        DownloadManager().mark_status(file_name, "paused")
        return {"file_name": file_name, "status": "paused"}

    @app.post("/queue/{file_name:path}/resume")
    def queue_resume(file_name: str) -> dict:
        _require_queue_item(file_name)
        DownloadManager().mark_status(file_name, "pending", attempts=0, last_error=None)
        return {"file_name": file_name, "status": "pending"}

    @app.post("/queue/{file_name:path}/retry")
    def queue_retry(file_name: str) -> dict:
        _require_queue_item(file_name)
        DownloadManager().mark_status(file_name, "pending", attempts=0, last_error=None)
        return {"file_name": file_name, "status": "pending"}

    @app.delete("/queue/{file_name:path}")
    def queue_delete(file_name: str) -> dict:
        _require_queue_item(file_name)
        DownloadManager()._remove_from_queue(file_name)
        return {"removed": True, "file_name": file_name}

    # -----------------------------------------------------------------
    # Updates (new seasons / episodes on tracked entries)
    # -----------------------------------------------------------------

    @app.get("/updates")
    def updates_list() -> list[dict]:
        from streamseeker.api.core.library.updates import collect_pending
        return collect_pending(LibraryStore())

    @app.post("/updates/{key:path}/dismiss")
    def updates_dismiss(key: str) -> dict:
        from streamseeker.api.core.library.updates import dismiss_updates
        if not dismiss_updates(LibraryStore(), KIND_LIBRARY, key):
            raise HTTPException(status_code=404, detail=f"not tracked: {key}")
        return {"dismissed": True, "key": key}

    @app.post("/updates/check")
    def updates_check(wait: bool = False) -> dict:
        """Manually trigger the update-check sweep (ignores the 24 h schedule).

        Runs in a background thread so the HTTP call returns fast; pass
        ``?wait=true`` to block until the sweep finishes and get stats.
        """
        from streamseeker.api.core.library.updates import UpdateChecker
        from streamseeker.api.handler import StreamseekerHandler
        checker = getattr(app.state, "update_checker", None) or UpdateChecker(StreamseekerHandler())

        if wait:
            results = checker.run_once()
            return {
                "checked": len(results),
                "changed": sum(1 for r in results if r.changed),
                "errors": sum(1 for r in results if r.error),
            }

        threading.Thread(target=checker.run_once, daemon=True,
                         name="ss-update-check-manual").start()
        return {"started": True}

    # -----------------------------------------------------------------
    # Library
    # -----------------------------------------------------------------

    @app.get("/library")
    def library_list() -> list[dict]:
        return LibraryStore().list(KIND_LIBRARY)

    @app.get("/library/state")
    def library_state(stream: str, slug: str) -> dict:
        return _library_state(stream, slug)

    @app.get("/library/{key:path}/poster")
    def library_poster(key: str):
        return _serve_asset(key, "poster.jpg")

    @app.get("/library/{key:path}/backdrop")
    def library_backdrop(key: str):
        return _serve_asset(key, "backdrop.jpg")

    @app.post("/library/{key:path}/refresh")
    def library_refresh(key: str) -> dict:
        entry = LibraryStore().get(KIND_LIBRARY, key)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"not in library: {key}")
        applied = MetadataResolver().enrich(key)
        return {"refreshed": applied, "key": key}

    @app.get("/library/{key:path}")
    def library_get(key: str) -> dict:
        entry = LibraryStore().get(KIND_LIBRARY, key)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"not in library: {key}")
        return entry

    # -----------------------------------------------------------------
    # Favorites — now a flag on library entries, not a separate store.
    # The ``/favorites`` endpoints remain for extension back-compat.
    # -----------------------------------------------------------------

    @app.get("/favorites")
    def favorites_list() -> list[dict]:
        return LibraryStore().list_collection(favorite_only=True)

    @app.post("/favorites", status_code=201)
    def favorites_add(req: FavoriteRequest) -> dict:
        entry = LibraryStore().set_favorite(f"{req.stream}::{req.slug}", True)
        key = entry["key"]
        threading.Thread(
            target=_safe_enrich, args=(key, KIND_LIBRARY), daemon=True
        ).start()
        return entry

    @app.get("/favorites/{key:path}/poster")
    def favorites_poster(key: str):
        return _serve_asset(key, "poster.jpg")

    @app.get("/favorites/{key:path}/backdrop")
    def favorites_backdrop(key: str):
        return _serve_asset(key, "backdrop.jpg")

    @app.post("/favorites/{key:path}/refresh")
    def favorites_refresh(key: str) -> dict:
        entry = LibraryStore().get(KIND_LIBRARY, key)
        if entry is None or not entry.get("favorite"):
            raise HTTPException(status_code=404, detail=f"no favorite: {key}")
        applied = MetadataResolver().enrich(key)
        return {"refreshed": applied, "key": key}

    @app.delete("/favorites/{key:path}")
    def favorites_remove(key: str) -> dict:
        store = LibraryStore()
        entry = store.get(KIND_LIBRARY, key)
        if entry is None or not entry.get("favorite"):
            raise HTTPException(status_code=404, detail=f"no favorite: {key}")
        store.set_favorite(key, False)
        return {"removed": True, "key": key}

    @app.post("/favorites/{key:path}/promote")
    def favorites_promote(key: str) -> dict:
        """Deprecated: no-op since favorites live in the library already.
        Kept for extension back-compat — returns the current entry."""
        entry = LibraryStore().get(KIND_LIBRARY, key)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"not tracked: {key}")
        return entry

    # -----------------------------------------------------------------
    # Server-Sent Events — live status stream for the extension popup
    # -----------------------------------------------------------------

    @app.get("/events")
    async def events(request: Request) -> StreamingResponse:
        async def stream():
            last_signature: Optional[str] = None
            # Poll every 500ms; only emit when summary or progress changed.
            # The timestamp is deliberately excluded from the dedup key so
            # we don't spam the client with pseudo-changes every tick.
            while True:
                if await request.is_disconnected():
                    break
                status = _build_status()
                signature = json.dumps(
                    {"summary": status.get("summary"), "progress": status.get("progress")},
                    sort_keys=True,
                )
                if signature != last_signature:
                    yield f"event: status\ndata: {json.dumps(status)}\n\n"
                    last_signature = signature
                await asyncio.sleep(0.5)

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


# Minimal placeholder dashboard. Gets extended in Paket F/H with real UI.
_DASHBOARD_HTML = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>StreamSeeker Daemon</title>
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; margin: 2rem; color: #222; }
    code { background: #eee; padding: 2px 6px; border-radius: 3px; }
    h1 { margin-bottom: 0.25rem; }
    small { color: #666; }
    ul { line-height: 1.8; }
  </style>
</head>
<body>
  <h1>StreamSeeker Daemon</h1>
  <small>Listening on <code>http://127.0.0.1:8765</code></small>
  <p>This dashboard will get a real UI in a later package. For now, use the
  JSON API or the CLI:</p>
  <ul>
    <li><a href="/status"><code>/status</code></a></li>
    <li><a href="/queue"><code>/queue</code></a></li>
    <li><a href="/library"><code>/library</code></a></li>
    <li><a href="/favorites"><code>/favorites</code></a></li>
    <li><a href="/docs"><code>/docs</code></a> — interactive API reference</li>
  </ul>
</body>
</html>
"""
