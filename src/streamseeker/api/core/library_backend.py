"""Backend facade for Library/Favorites operations.

Transparently routes to either the local ``LibraryStore`` (daemon absent)
or the daemon's HTTP API (daemon running). CLI commands should use this
instead of ``LibraryStore`` directly so the right writer is chosen.

Read operations fall back to the local store if the daemon call fails —
worst case the user sees slightly stale data instead of a hard error.
Write operations propagate daemon errors so the user knows the mutation
didn't take effect.
"""

from __future__ import annotations

from streamseeker.api.core import daemon_client
from streamseeker.api.core.library import LibraryStore
from streamseeker.api.core.library.store import KIND_FAVORITES, KIND_LIBRARY


class LibraryBackend:
    """Proxy that dispatches to the daemon when alive, else local store."""

    def __init__(self, *, prefer_daemon: bool | None = None) -> None:
        self._store = LibraryStore()
        # Decide once per instance to avoid repeated pings
        self._use_daemon = (
            prefer_daemon if prefer_daemon is not None else daemon_client.is_daemon_running()
        )

    @property
    def uses_daemon(self) -> bool:
        return self._use_daemon

    # --- Favorites --------------------------------------------------

    def favorites_list(self) -> list[dict]:
        if self._use_daemon:
            try:
                return daemon_client.favorites_list()
            except Exception:
                pass
        return self._store.list(KIND_FAVORITES)

    def favorites_search(self, term: str) -> list[dict]:
        # The daemon doesn't expose search; filter its list locally.
        rows = self.favorites_list()
        needle = term.strip().lower()
        if not needle:
            return []
        return [
            r for r in rows
            if needle in (r.get("title") or "").lower() or needle in (r.get("slug") or "").lower()
        ]

    def favorites_get(self, key: str) -> dict | None:
        # No per-key favorite endpoint on the daemon; local read is fine either way.
        return self._store.get(KIND_FAVORITES, key)

    def favorites_add(self, stream: str, slug: str) -> dict:
        if self._use_daemon:
            return daemon_client.favorites_add(stream, slug)
        return self._store.add(KIND_FAVORITES, {"stream": stream, "slug": slug})

    def favorites_remove(self, key: str) -> bool:
        if self._use_daemon:
            try:
                daemon_client.favorites_remove(key)
                return True
            except daemon_client.DaemonError as exc:
                if exc.status_code == 404:
                    return False
                raise
        return self._store.remove(KIND_FAVORITES, key)

    def favorites_promote(self, key: str) -> dict:
        if self._use_daemon:
            return daemon_client.favorites_promote(key)
        return self._store.move_favorite_to_library(key)

    # --- Library ----------------------------------------------------

    def library_list(self) -> list[dict]:
        if self._use_daemon:
            try:
                return daemon_client.library_list()
            except Exception:
                pass
        return self._store.list(KIND_LIBRARY)

    def library_search(self, term: str) -> list[dict]:
        rows = self.library_list()
        needle = term.strip().lower()
        if not needle:
            return []
        return [
            r for r in rows
            if needle in (r.get("title") or "").lower() or needle in (r.get("slug") or "").lower()
        ]

    def library_get(self, key: str) -> dict | None:
        if self._use_daemon:
            try:
                return daemon_client.library_get(key)
            except daemon_client.DaemonError as exc:
                if exc.status_code == 404:
                    return None
                # Fall through to local
        return self._store.get(KIND_LIBRARY, key)

    def library_remove(self, key: str) -> bool:
        # No DELETE /library endpoint yet — always go local. The single-writer
        # guarantee still holds: the daemon polls the queue, not the library,
        # so removing an entry locally is safe.
        return self._store.remove(KIND_LIBRARY, key)
