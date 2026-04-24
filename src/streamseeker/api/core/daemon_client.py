"""Thin HTTP client for the running StreamSeeker daemon.

Used by CLI commands to route mutations through the daemon when one is
alive, so there's a single writer on the Queue/Library/Favorites files.
When no daemon is running, callers fall back to direct store access.
"""

from __future__ import annotations

from typing import Any

import requests

from streamseeker.daemon.lifecycle import DAEMON_HOST, DAEMON_PORT

BASE_URL = f"http://{DAEMON_HOST}:{DAEMON_PORT}"
_PING_TIMEOUT = 0.2  # seconds
_CALL_TIMEOUT = 5.0


class DaemonError(RuntimeError):
    """Raised when a daemon call fails with a non-2xx response."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(f"HTTP {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


def is_daemon_running(*, timeout: float = _PING_TIMEOUT) -> bool:
    """Return True if the daemon's `/status` endpoint responds within the timeout."""
    try:
        response = requests.get(f"{BASE_URL}/status", timeout=timeout)
        return response.status_code == 200
    except requests.RequestException:
        return False


def _get(path: str, **kwargs) -> Any:
    r = requests.get(f"{BASE_URL}{path}", timeout=_CALL_TIMEOUT, **kwargs)
    _raise_if_error(r)
    return r.json()


def _post(path: str, payload: dict | None = None) -> Any:
    r = requests.post(f"{BASE_URL}{path}", json=payload or {}, timeout=_CALL_TIMEOUT)
    _raise_if_error(r)
    return r.json() if r.content else None


def _delete(path: str) -> Any:
    r = requests.delete(f"{BASE_URL}{path}", timeout=_CALL_TIMEOUT)
    _raise_if_error(r)
    return r.json() if r.content else None


def _raise_if_error(response: requests.Response) -> None:
    if response.ok:
        return
    try:
        detail = response.json().get("detail") or response.text
    except ValueError:
        detail = response.text
    raise DaemonError(response.status_code, str(detail))


# ---------------------------------------------------------------------
# Convenience wrappers — one per endpoint we use from the CLI
# ---------------------------------------------------------------------


def version() -> dict:
    return _get("/version")


def status() -> dict:
    return _get("/status")


# Queue --------------------------------------------------------------


def queue_list() -> list[dict]:
    return _get("/queue")


def queue_add(stream: str, slug: str, *, type: str = "staffel",
              season: int = 0, episode: int = 0, language: str = "german",
              preferred_provider: str | None = None, file_name: str | None = None) -> dict:
    body = {
        "stream": stream, "slug": slug, "type": type,
        "season": season, "episode": episode, "language": language,
    }
    if preferred_provider:
        body["preferred_provider"] = preferred_provider
    if file_name:
        body["file_name"] = file_name
    return _post("/queue", body)


# Library ------------------------------------------------------------


def library_list() -> list[dict]:
    return _get("/library")


def library_get(key: str) -> dict:
    return _get(f"/library/{key}")


def library_state(stream: str, slug: str) -> dict:
    return _get("/library/state", params={"stream": stream, "slug": slug})


# Favorites ----------------------------------------------------------


def favorites_list() -> list[dict]:
    return _get("/favorites")


def favorites_add(stream: str, slug: str) -> dict:
    return _post("/favorites", {"stream": stream, "slug": slug})


def favorites_remove(key: str) -> dict | None:
    return _delete(f"/favorites/{key}")


def favorites_promote(key: str) -> dict:
    return _post(f"/favorites/{key}/promote")


# SSE stream ---------------------------------------------------------


def events(timeout: float | None = None):
    """Yield SSE events from /events.

    Each yielded item is a dict with ``event`` and ``data`` keys.
    Breaks out when the HTTP connection closes.
    """
    r = requests.get(f"{BASE_URL}/events", stream=True, timeout=timeout)
    r.raise_for_status()
    event_name: str | None = None
    data_lines: list[str] = []
    try:
        for raw in r.iter_lines(decode_unicode=True):
            if raw is None:
                continue
            if raw == "":
                if event_name is not None or data_lines:
                    yield {"event": event_name or "message", "data": "\n".join(data_lines)}
                event_name = None
                data_lines = []
                continue
            if raw.startswith("event:"):
                event_name = raw[6:].strip()
            elif raw.startswith("data:"):
                data_lines.append(raw[5:].lstrip())
    finally:
        r.close()
