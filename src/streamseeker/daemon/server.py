"""FastAPI application factory for the StreamSeeker daemon."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import Body, FastAPI, HTTPException, Request
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


def _ensure_library_stub_async(stream: str, slug: str, type_: str) -> None:
    """Upsert a minimal library entry (slug-as-title placeholder) and kick
    off TMDb/AniList enrichment in a background thread.

    This is what makes a freshly-enqueued show appear in the Sammlung tab
    immediately, with cover/description filling in a couple of seconds
    later — instead of only after the first episode finishes downloading.
    Non-blocking: never raises into the request handler.
    """
    if not stream or not slug:
        return
    key = f"{stream}::{slug}"

    def _worker() -> None:
        try:
            store = LibraryStore()
            existing = store.get(KIND_LIBRARY, key)
            if not existing:
                # Title left as the slug; the resolver overwrites it once
                # TMDb/AniList have a match. ``add`` is upsert-safe.
                store.add(KIND_LIBRARY, {
                    "key": key,
                    "stream": stream,
                    "slug": slug,
                    "title": slug.replace("-", " ").title(),
                    "type": type_ or "staffel",
                })
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"library stub upsert failed for {key}: {exc}")
            return
        _safe_enrich(key, KIND_LIBRARY)
        _populate_season_totals(stream, slug, type_)

    threading.Thread(target=_worker, name=f"ss-enqueue-stub-{slug}", daemon=True).start()


def _populate_season_totals(stream: str, slug: str, type_: str) -> None:
    """Ask the stream how many episodes each season has and write the totals
    into the Library entry. Without this, ``seasons[N].episode_count`` only
    grows to whatever has been *downloaded*, so the Sammlung-card and detail
    overlay show "1/1" instead of "1/10". Best-effort; never raises."""
    try:
        if (type_ or "").lower() == "filme":
            return
        from streamseeker.api.handler import StreamseekerHandler

        handler = StreamseekerHandler()
        impl = handler._streams.get(stream)
        if impl is None:
            return
        impl.set_config(handler.config)
        seasons = impl.search_seasons(slug, "staffel") or []
        counts: dict[int, int] = {}
        for season in seasons:
            # Season 0 on s.to is the "Filme"-section; the extension/UI
            # doesn't surface movies through the seasons grid yet, so skip
            # them here to keep the totals reflect only real TV seasons.
            if int(season) == 0:
                continue
            try:
                episodes = impl.search_episodes(slug, "staffel", season) or []
            except Exception:  # noqa: BLE001 — keep going on per-season failure
                continue
            counts[int(season)] = len(episodes)
        if counts:
            LibraryStore().update_season_totals(f"{stream}::{slug}", counts)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"season totals fetch failed for {stream}::{slug}: {exc}")


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
    scope: Optional[str] = None  # "single" | "season" | "season_from" | "from" | "all" | "missing"
    type: str = "staffel"
    season: int = 0
    episode: int = 0
    language: str = "german"
    preferred_provider: Optional[str] = None
    file_name: Optional[str] = None


class SettingsPatch(BaseModel):
    config: Optional[dict] = None
    tmdb_api_key: Optional[str] = None


class MarkRequest(BaseModel):
    stream: str
    slug: str
    scope: Optional[str] = None
    type: str = "staffel"
    season: int = 0
    episode: int = 0


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _format_key(stream: str, slug: str) -> str:
    return f"{stream}::{slug}"


def _build_status() -> dict:
    manager = DownloadManager()
    payload = {
        "summary": manager.queue_summary(),
        "progress": manager.get_progress(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    # Surface the queue-processor circuit breaker so the popup can render
    # a banner ("Pausiert bis HH:MM — Anbieter zickt"). Optional in the
    # response shape so old extensions don't trip on the extra field.
    try:
        from streamseeker.api.core.downloader.processor import QueueProcessor
        payload["circuit"] = QueueProcessor().circuit_state()
    except Exception:  # noqa: BLE001 — status must never raise
        payload["circuit"] = {"paused": False}
    return payload


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


_LIBRARY_STATE_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_LIBRARY_STATE_TTL = 2.0  # seconds — fast enough for UI, short enough that
#                         SSE-driven updates surface within ~2s.
_LIBRARY_STATE_LOCK = threading.Lock()

# Progress state for the "Metadaten neu laden" button in the popup.
# Polled via GET /library/refresh-all/status; the popup uses it to drive
# a progress bar and re-enable the button when running flips to False.
_REFRESH_ALL_LOCK = threading.Lock()
_REFRESH_ALL_STATE: dict = {
    "running": False,
    "total": 0,
    "current": 0,
    "success": 0,
    "started_at": None,
    "finished_at": None,
    "cancel_requested": False,
}


def _library_state_cached(stream: str, slug: str) -> dict:
    """TTL-cached wrapper around ``_library_state``.

    Under load — e.g. five ffmpeg workers downloading + post-success
    enrichment threads hammering the library lock — the raw
    ``_library_state`` call can block noticeably because it takes the
    LibraryStore lock + reads queue.json. The content script fires this
    endpoint right on page load, where a 0.5–3 s delay is painful.

    We cache the result for a couple of seconds. Live transitions still
    flow via SSE, so the brief staleness is invisible to the user.
    """
    key = (stream, slug)
    now = time.monotonic()
    with _LIBRARY_STATE_LOCK:
        cached = _LIBRARY_STATE_CACHE.get(key)
        if cached and now - cached[0] < _LIBRARY_STATE_TTL:
            return cached[1]

    value = _library_state(stream, slug)

    with _LIBRARY_STATE_LOCK:
        _LIBRARY_STATE_CACHE[key] = (now, value)
        # Opportunistic GC — drop entries that haven't been read in a while.
        if len(_LIBRARY_STATE_CACHE) > 512:
            stale_cutoff = now - _LIBRARY_STATE_TTL * 10
            for k, (ts, _) in list(_LIBRARY_STATE_CACHE.items()):
                if ts < stale_cutoff:
                    _LIBRARY_STATE_CACHE.pop(k, None)
    return value


def _invalidate_library_state_cache(stream: str | None = None, slug: str | None = None) -> None:
    """Drop cached entries when the underlying data changes.

    Called from write paths (``/queue`` mutations, ``/library/mark``,
    ``/favorites``). If ``stream``/``slug`` aren't provided we just
    wipe everything — cheap since the cache is small and refills in <5ms.
    """
    with _LIBRARY_STATE_LOCK:
        if stream is None or slug is None:
            _LIBRARY_STATE_CACHE.clear()
        else:
            _LIBRARY_STATE_CACHE.pop((stream, slug), None)


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
            r"|https://(aniworld\.to|s\.to)"
            r")$"
        ),
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def _activate_language_on_startup() -> None:
        from streamseeker.i18n import init_from_config
        active = init_from_config()
        logger.info(f"language activated: {active}")

    @app.on_event("startup")
    def _sync_browser_extension_on_startup() -> None:
        # Keep ~/.streamseeker/extension/ in step with the bundled source so
        # CLI upgrades pull the new extension without manual install steps.
        # The browser extension picks up the change via /extension/version
        # and reloads itself.
        from streamseeker.distribution import sync_extension
        try:
            result = sync_extension()
            if result.action == "updated":
                logger.info(
                    f"extension updated on disk: "
                    f"{result.installed_version} → {result.bundled_version}"
                )
            elif result.action == "installed":
                logger.info(
                    f"extension installed on disk (version {result.bundled_version})"
                )
            elif result.action == "skipped_symlink":
                logger.info("extension target is a dev symlink — skipping auto-sync")
        except Exception as exc:  # noqa: BLE001 — startup must not fail because of this
            logger.warning(f"extension auto-sync failed: {exc}")

    @app.on_event("startup")
    def _verify_library_index_on_startup() -> None:
        """Runs before anything else touches the library.

        The per-series JSON files are the source of truth; ``index.json``
        is a cache. If the cache has drifted from disk (truncated write,
        multi-process race, corrupt file), rebuild it from disk so clients
        never see a shrunk library just because the index is stale.
        """
        try:
            store = LibraryStore()
            disk_count = store._disk_entry_count(KIND_LIBRARY)  # noqa: SLF001
            index_count = len(store._read_index(KIND_LIBRARY))  # noqa: SLF001
            if index_count < disk_count:
                rows = store.rebuild_index(KIND_LIBRARY)
                logger.info(
                    f"library index rebuilt on startup: {index_count} → {len(rows)} entries"
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"library index verification failed: {exc}")

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

    @app.on_event("startup")
    def _start_watchdog() -> None:
        from streamseeker.daemon.watchdog import Watchdog
        from streamseeker.daemon.lifecycle import DAEMON_HOST, DAEMON_PORT
        try:
            app.state.watchdog = Watchdog(host=DAEMON_HOST, port=DAEMON_PORT)
            app.state.watchdog.start()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"watchdog failed to start: {exc}")

    @app.on_event("shutdown")
    def _stop_watchdog() -> None:
        wd = getattr(app.state, "watchdog", None)
        if wd:
            try:
                wd.stop()
            except Exception:  # noqa: BLE001
                pass

    # -----------------------------------------------------------------
    # Meta
    # -----------------------------------------------------------------

    @app.get("/version")
    def version() -> dict:
        from streamseeker.distribution import installed_extension_version
        return {
            "cli": get_version(),
            "extension": installed_extension_version(),
        }

    @app.get("/extension/version")
    def extension_version() -> dict:
        # Used by the extension's background worker to detect when an
        # auto-synced newer copy is on disk and trigger chrome.runtime.reload().
        from streamseeker.distribution import installed_extension_version
        return {"version": installed_extension_version()}

    @app.get("/health")
    def health() -> dict:
        # Intentionally minimal: no locks, no disk reads. Used by the
        # in-process watchdog to detect event-loop hangs.
        return {"ok": True, "ts": time.time()}

    @app.get("/status")
    def status() -> dict:
        return _build_status()

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        return _DASHBOARD_HTML

    # -----------------------------------------------------------------
    # Settings — exposes config.json + credentials presence to the
    # extension's Settings tab. We deliberately never return raw API
    # keys: the UI only needs to know whether one is set.
    # -----------------------------------------------------------------

    # Allow-list of config.json keys the extension may write to. Anything
    # outside this list is silently dropped on PATCH so a compromised
    # extension can't, e.g., flip output_folder to /tmp/evil.
    _SETTINGS_WRITABLE = {
        "preferred_provider",
        "max_concurrent",
        "max_retries",
        "ddos_limit",
        "ddos_timer",
        "language",
        "overlay_collapsed_default",
    }

    def _read_config_safely() -> dict:
        cfg_file = paths.config_file()
        if not cfg_file.is_file():
            return {}
        try:
            return json.loads(cfg_file.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_config(data: dict) -> None:
        from streamseeker.api.core.library.store import _atomic_write_json  # type: ignore
        _atomic_write_json(paths.config_file(), data)

    @app.get("/settings")
    def settings_get() -> dict:
        from streamseeker.i18n import SUPPORTED_LANGUAGES, DEFAULT_LANGUAGE
        cfg = _read_config_safely()
        creds = paths.load_credentials()
        return {
            "config": {
                **cfg,
                "language": cfg.get("language") or DEFAULT_LANGUAGE,
                # New stream-page overlay starts collapsed unless overridden;
                # the per-tab toggle is still allowed via localStorage.
                "overlay_collapsed_default": bool(
                    cfg.get("overlay_collapsed_default", True)
                ),
            },
            "supported_languages": list(SUPPORTED_LANGUAGES),
            "credentials": {
                # Boolean flags only — never echo the actual key.
                "tmdb": bool(creds.get("tmdb_api_key")),
            },
            "paths": {
                "home": paths.display_path(paths.home()),
                "config_file": paths.display_path(paths.config_file()),
                "credentials_file": paths.display_path(paths.credentials_file()),
                "downloads": paths.display_path(paths.downloads_dir()),
                "library": paths.display_path(paths.library_dir()),
            },
            "writable_keys": sorted(_SETTINGS_WRITABLE),
        }

    @app.patch("/settings")
    def settings_patch(payload: SettingsPatch) -> dict:
        from streamseeker.i18n import SUPPORTED_LANGUAGES, set_language
        applied: dict = {}
        if payload.config:
            cfg = _read_config_safely()
            for k, v in payload.config.items():
                if k not in _SETTINGS_WRITABLE:
                    continue
                # Reject unknown language codes — saving "fr" without a
                # locale bundle would just silently fall back to English.
                if k == "language" and v not in SUPPORTED_LANGUAGES:
                    continue
                cfg[k] = v
                applied[k] = v
            _write_config(cfg)
            # Live-apply language so subsequent log lines speak it.
            if "language" in applied:
                set_language(applied["language"])

        if payload.tmdb_api_key is not None:
            creds_file = paths.credentials_file()
            current = paths.load_credentials() if creds_file.is_file() else {}
            if payload.tmdb_api_key.strip() == "":
                current.pop("tmdb_api_key", None)
            else:
                current["tmdb_api_key"] = payload.tmdb_api_key.strip()
            creds_file.parent.mkdir(parents=True, exist_ok=True)
            creds_file.write_text(json.dumps(current, indent=2))
            try:
                creds_file.chmod(0o600)
            except OSError:
                pass
            applied["tmdb_api_key"] = "(updated)"

        return {"applied": applied}

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
        # directly.
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
            if scope == "missing":
                count = handler.enqueue_missing(
                    req.stream, provider, req.slug, language, req.type,
                )
            elif req.type == "filme" or scope == "single":
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

        # Make the show visible in the Sammlung tab immediately, even before
        # the first download finishes. Upsert a minimal library entry and
        # kick off async metadata enrichment so cover/description/genres
        # appear within a couple of seconds.
        if count > 0:
            _ensure_library_stub_async(req.stream, req.slug, req.type)

        _invalidate_library_state_cache(req.stream, req.slug)
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
        _invalidate_library_state_cache()
        return {"file_name": file_name, "status": "paused"}

    @app.post("/queue/{file_name:path}/resume")
    def queue_resume(file_name: str) -> dict:
        _require_queue_item(file_name)
        DownloadManager().mark_status(file_name, "pending", attempts=0, last_error=None)
        _invalidate_library_state_cache()
        return {"file_name": file_name, "status": "pending"}

    @app.post("/queue/{file_name:path}/retry")
    def queue_retry(file_name: str) -> dict:
        _require_queue_item(file_name)
        DownloadManager().mark_status(file_name, "pending", attempts=0, last_error=None)
        _invalidate_library_state_cache()
        return {"file_name": file_name, "status": "pending"}

    @app.delete("/queue/{file_name:path}")
    def queue_delete(file_name: str) -> dict:
        _require_queue_item(file_name)
        DownloadManager()._remove_from_queue(file_name)
        _invalidate_library_state_cache()
        return {"removed": True, "file_name": file_name}

    @app.post("/queue/resume")
    def queue_resume_paused() -> dict:
        """Manually clear a circuit-breaker pause so downloads resume now,
        instead of waiting out the cooldown. Idempotent — no-op if the
        breaker isn't tripped."""
        from streamseeker.api.core.downloader.processor import QueueProcessor
        was_paused = QueueProcessor().resume_now()
        return {"resumed": was_paused}

    # -----------------------------------------------------------------
    # Updates (new seasons / episodes on tracked entries)
    # -----------------------------------------------------------------

    @app.get("/updates")
    def updates_list() -> list[dict]:
        from streamseeker.api.core.library.updates import collect_pending
        return collect_pending(LibraryStore())

    @app.post("/updates/dismiss-all")
    def updates_dismiss_all() -> dict:
        from streamseeker.api.core.library.updates import dismiss_all_updates
        cleared = dismiss_all_updates(LibraryStore(), KIND_LIBRARY)
        return {"dismissed": cleared}

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
        # Sort across all providers so the user sees one cohesive,
        # alphabetically-ordered list — by default the on-disk index is
        # grouped by stream-dir (aniworldto, sto), which made later
        # providers always appear at the bottom regardless of title.
        rows = LibraryStore().list(KIND_LIBRARY)
        return sorted(
            rows,
            key=lambda r: (r.get("title") or r.get("slug") or "").casefold(),
        )

    @app.get("/library/state")
    def library_state(stream: str, slug: str) -> dict:
        return _library_state_cached(stream, slug)

    @app.get("/library/{key:path}/poster")
    def library_poster(key: str):
        return _serve_asset(key, "poster.jpg")

    @app.get("/library/{key:path}/backdrop")
    def library_backdrop(key: str):
        return _serve_asset(key, "backdrop.jpg")

    @app.post("/library/mark", status_code=201)
    def library_mark(req: MarkRequest) -> dict:
        """Mark episodes/movies as already-owned without downloading.

        Useful when the user already has files on disk from before using
        StreamSeeker — they can seed the library so the update checker
        picks it up, covers get fetched and downloads aren't duplicated.
        """
        from streamseeker.api.handler import StreamseekerHandler

        handler = StreamseekerHandler()
        key = f"{req.stream}::{req.slug}"
        store = LibraryStore()
        scope = (req.scope or _infer_scope(req)).lower()
        marked = 0

        def _mark_episode(season: int, episode: int) -> None:
            nonlocal marked
            store.mark_episode_downloaded(key, season, episode)
            marked += 1

        def _mark_movie(movie_num: int) -> None:
            nonlocal marked
            store.mark_movie_downloaded(key, movie_num)
            marked += 1

        try:
            if req.type == "filme":
                info = handler.search(req.stream, req.slug) or {}
                movies = list(info.get("movies") or [])
                if scope == "single":
                    _mark_movie(req.episode or 1)
                else:
                    for m in (movies or [1]):
                        _mark_movie(m)
            else:
                info = handler.search(req.stream, req.slug) or {}
                seasons = list(info.get("series") or [])

                # Episode-count lookup with simple cache
                episodes_cache: dict[int, list[int]] = {}
                def _episodes_for(season: int) -> list[int]:
                    if season not in episodes_cache:
                        episodes_cache[season] = list(
                            handler.search_episodes(req.stream, req.slug, "staffel", season) or []
                        )
                    return episodes_cache[season]

                if scope == "single":
                    _mark_episode(req.season, req.episode)
                elif scope == "season":
                    for ep in _episodes_for(req.season):
                        _mark_episode(req.season, ep)
                elif scope == "season_from":
                    for ep in _episodes_for(req.season):
                        if ep >= req.episode:
                            _mark_episode(req.season, ep)
                elif scope == "from":
                    for season in seasons:
                        if season < req.season:
                            continue
                        for ep in _episodes_for(season):
                            if season == req.season and ep < req.episode:
                                continue
                            _mark_episode(season, ep)
                else:  # "all"
                    for season in seasons:
                        for ep in _episodes_for(season):
                            _mark_episode(season, ep)

            # Trigger metadata enrichment so covers get fetched.
            threading.Thread(
                target=_safe_enrich, args=(key, KIND_LIBRARY), daemon=True
            ).start()
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"mark failed for {key}: {exc}")
            raise HTTPException(status_code=500, detail=f"mark failed: {exc}") from exc

        _invalidate_library_state_cache(req.stream, req.slug)
        return {"marked": marked, "key": key}

    @app.post("/library/refresh-all")
    def library_refresh_all(reset: bool = True, delay: float = 1.5) -> dict:
        """Re-run metadata enrichment for every library entry, paced.

        Used when the user changes UI language and wants the on-disk
        metadata cache repopulated with translations. Runs in a background
        thread with ``delay`` seconds between entries so external APIs
        (TMDb 50 req/s, AniList 30 req/min) are never hit hard. Returns
        immediately with the number of entries queued; the popup polls
        ``GET /library/refresh-all/status`` for the progress bar.
        """
        store = LibraryStore()
        rows = [row for row in store.list(KIND_LIBRARY) if row.get("key")]
        keys = [row.get("key") for row in rows]
        delay_seconds = max(0.0, float(delay))

        with _REFRESH_ALL_LOCK:
            if _REFRESH_ALL_STATE.get("running"):
                # Already in flight — surface that instead of starting a duplicate
                return {
                    "queued": _REFRESH_ALL_STATE.get("total", 0),
                    "delay_seconds": delay_seconds,
                    "already_running": True,
                }
            _REFRESH_ALL_STATE.update({
                "running": True,
                "total": len(rows),
                "current": 0,
                "success": 0,
                "started_at": time.time(),
                "finished_at": None,
                "cancel_requested": False,
            })

        def _worker() -> None:
            resolver = MetadataResolver()
            success = 0
            try:
                for index, row in enumerate(rows):
                    with _REFRESH_ALL_LOCK:
                        if _REFRESH_ALL_STATE.get("cancel_requested"):
                            logger.info(
                                f"refresh-all cancelled at {index}/{len(rows)}"
                            )
                            break
                    k = row.get("key")
                    try:
                        if resolver.enrich(k, reset=reset):
                            success += 1
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(f"refresh-all: enrich failed for {k}: {exc}")
                    # Refresh real episode totals from the stream too — that's
                    # what makes the Sammlung-card show "1/10" instead of "1/1"
                    # for entries that were created before the auto-populate
                    # logic existed. Movies (type=='filme') skip the scrape.
                    stream = row.get("stream")
                    slug = row.get("slug")
                    row_type = row.get("type") or "staffel"
                    if stream and slug and row_type != "filme":
                        try:
                            _populate_season_totals(stream, slug, row_type)
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(f"refresh-all: totals failed for {k}: {exc}")
                    with _REFRESH_ALL_LOCK:
                        _REFRESH_ALL_STATE["current"] = index + 1
                        _REFRESH_ALL_STATE["success"] = success
                    if delay_seconds and index < len(rows) - 1:
                        time.sleep(delay_seconds)
                logger.info(
                    f"refresh-all completed: {success}/{len(rows)} entries enriched"
                )
            finally:
                with _REFRESH_ALL_LOCK:
                    _REFRESH_ALL_STATE["running"] = False
                    _REFRESH_ALL_STATE["finished_at"] = time.time()

        threading.Thread(target=_worker, name="ss-refresh-all", daemon=True).start()
        return {"queued": len(keys), "delay_seconds": delay_seconds}

    @app.get("/library/refresh-all/status")
    def library_refresh_all_status() -> dict:
        """Snapshot of the current/last refresh-all progress so the popup
        can drive a progress bar without holding an SSE connection."""
        with _REFRESH_ALL_LOCK:
            return dict(_REFRESH_ALL_STATE)

    @app.post("/library/refresh-all/cancel")
    def library_refresh_all_cancel() -> dict:
        """Soft-cancel a stuck refresh-all run. Sets a flag the worker
        checks at the top of each iteration; the active enrich call
        finishes (we don't kill threads), then the loop exits and the
        button becomes available again. Idempotent — calling it when
        nothing is running is a no-op."""
        with _REFRESH_ALL_LOCK:
            was_running = bool(_REFRESH_ALL_STATE.get("running"))
            if was_running:
                _REFRESH_ALL_STATE["cancel_requested"] = True
        return {"cancelled": was_running}

    @app.post("/library/{key:path}/refresh")
    def library_refresh(
        key: str,
        title: Optional[str] = None,
        year: Optional[int] = None,
        reset: bool = False,
    ) -> dict:
        """Re-run the provider chain for ``key``.

        Query params let the caller steer an ambiguous search —
        e.g. ``?title=Stargate%20SG-1&year=1997&reset=true`` to replace
        the previous "Stargate 2025" match.
        """
        entry = LibraryStore().get(KIND_LIBRARY, key)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"not in library: {key}")
        applied = MetadataResolver().enrich(
            key,
            title_override=title,
            year_override=year,
            reset=reset,
        )
        # Also re-scrape the season structure so x/y on the Sammlung card
        # and detail overlay reflect the actual episode count, not just
        # whatever has been downloaded so far. Movies skip this step.
        stream = entry.get("stream")
        slug = entry.get("slug")
        row_type = entry.get("type") or "staffel"
        if stream and slug and row_type != "filme":
            try:
                _populate_season_totals(stream, slug, row_type)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"refresh: totals failed for {key}: {exc}")
        return {"refreshed": applied, "key": key}

    @app.get("/library/{key:path}")
    def library_get(key: str) -> dict:
        entry = LibraryStore().get(KIND_LIBRARY, key)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"not in library: {key}")
        return entry

    # Maps a stream-slug to the on-disk subfolder used by ``build_file_path``.
    # Centralised here so the open-folder endpoint can derive the right
    # path without round-tripping through the stream classes (which need
    # network access to instantiate).
    _STREAM_TYPE_DIR = {
        "aniworldto": "anime",
        "sto": "serie",
    }

    def _downloads_folder_for(entry: dict) -> "Path":
        from pathlib import Path
        slug = entry.get("slug") or ""
        stream = entry.get("stream") or ""
        sub = _STREAM_TYPE_DIR.get(stream)
        if sub is None:
            return paths.downloads_dir()
        return paths.downloads_dir() / sub / slug

    def _open_in_file_manager(path: "Path") -> str:
        """Spawn the platform's file manager pointed at ``path``.

        Falls back to ``path.parent`` if the requested folder doesn't exist
        — better to land in the parent than throw 500.
        """
        import subprocess
        import sys
        if not path.exists():
            path = path.parent if path.parent.exists() else paths.downloads_dir()
        target = str(path)
        if sys.platform == "darwin":
            subprocess.Popen(["open", target])
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", target])
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", target])
        else:
            raise HTTPException(status_code=501, detail=f"unsupported platform: {sys.platform}")
        return target

    @app.post("/library/{key:path}/open-folder")
    def library_open_folder(key: str) -> dict:
        """Open the user's local download folder for ``key`` in Finder /
        Explorer / xdg. Daemon must be running on the user's host (it is —
        bound to 127.0.0.1 only) for this to make sense.
        """
        entry = LibraryStore().get(KIND_LIBRARY, key)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"not in library: {key}")
        target = _open_in_file_manager(_downloads_folder_for(entry))
        return {"opened": target, "key": key}

    @app.delete("/library/{key:path}")
    def library_delete(key: str) -> dict:
        """Remove a library entry + its asset folder (poster, backdrop).
        Does **not** touch downloaded media files in ``~/.streamseeker/downloads/``.
        """
        removed = LibraryStore().remove(KIND_LIBRARY, key)
        if not removed:
            raise HTTPException(status_code=404, detail=f"not in library: {key}")
        _invalidate_library_state_cache()
        return {"removed": True, "key": key}

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
        _invalidate_library_state_cache(req.stream, req.slug)
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
        _invalidate_library_state_cache()
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
            ticks_since_keepalive = 0
            # Send an SSE comment line every ~20s so MV3 service workers
            # (which time out after 30s of no network activity) stay alive
            # while the queue is idle. Browsers ignore SSE comment lines.
            keepalive_every = 40  # 40 * 0.5s = 20s
            while True:
                if await request.is_disconnected():
                    break
                status = _build_status()
                # Include the circuit-breaker state in the dedup signature
                # so a "paused"/"resumed" transition pushes immediately.
                signature = json.dumps(
                    {
                        "summary": status.get("summary"),
                        "progress": status.get("progress"),
                        "circuit": status.get("circuit"),
                    },
                    sort_keys=True,
                )
                if signature != last_signature:
                    yield f"event: status\ndata: {json.dumps(status)}\n\n"
                    last_signature = signature
                    ticks_since_keepalive = 0
                else:
                    ticks_since_keepalive += 1
                    if ticks_since_keepalive >= keepalive_every:
                        yield ": keepalive\n\n"
                        ticks_since_keepalive = 0
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
