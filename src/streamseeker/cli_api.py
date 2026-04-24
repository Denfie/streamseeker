"""Public Python API for StreamSeeker.

External scripts (or other tools in the same workspace) can import from
this module to talk to a running daemon — or, when no daemon is up, to the
local store directly. The facade keeps both paths behind one signature so
scripts don't have to know whether a daemon is running.

Usage:

    from streamseeker import cli_api

    if cli_api.is_daemon_running():
        print(cli_api.status())
    cli_api.favorite_add("aniworldto", "oshi-no-ko")
    cli_api.enqueue("sto", "breaking-bad", season=1, episode=1)

The legacy ``python -m streamseeker.cli_api`` entry point is retained at the
bottom for backwards compatibility.
"""

from __future__ import annotations

import logging
from typing import Iterator

from streamseeker.api.core import daemon_client
from streamseeker.api.core.library_backend import LibraryBackend
from streamseeker.api.core.logger import Logger


# ---------------------------------------------------------------------
# Daemon discovery
# ---------------------------------------------------------------------


def is_daemon_running() -> bool:
    """Cheap ping of the local daemon's /status endpoint."""
    return daemon_client.is_daemon_running()


def status() -> dict:
    """Return the full daemon status dict (summary + progress + timestamp)."""
    return daemon_client.status()


def version() -> dict:
    """Return ``{'cli': '<semver>'}`` from the daemon."""
    return daemon_client.version()


# ---------------------------------------------------------------------
# Queue mutations
# ---------------------------------------------------------------------


def enqueue(
    stream: str,
    slug: str,
    *,
    type: str = "staffel",
    season: int = 0,
    episode: int = 0,
    language: str = "german",
    preferred_provider: str | None = None,
    file_name: str | None = None,
) -> dict:
    """Enqueue a download item. Uses the daemon when alive, else writes the
    local queue directly."""
    if is_daemon_running():
        return daemon_client.queue_add(
            stream, slug,
            type=type, season=season, episode=episode,
            language=language, preferred_provider=preferred_provider,
            file_name=file_name,
        )
    from streamseeker.api.core.downloader.manager import DownloadManager
    item = {
        "stream_name": stream, "name": slug,
        "type": type, "season": season, "episode": episode,
        "language": language,
        "preferred_provider": preferred_provider,
        "file_name": file_name or f"{stream}/{slug}-s{season}e{episode}",
    }
    DownloadManager().enqueue(item)
    return {"enqueued": True, "file_name": item["file_name"]}


def queue_list() -> list[dict]:
    if is_daemon_running():
        return daemon_client.queue_list()
    from streamseeker.api.core.downloader.manager import DownloadManager
    return DownloadManager().get_queue()


# ---------------------------------------------------------------------
# Library & Favorites
# ---------------------------------------------------------------------


def favorite_add(stream: str, slug: str) -> dict:
    return LibraryBackend().favorites_add(stream, slug)


def favorite_remove(key: str) -> bool:
    return LibraryBackend().favorites_remove(key)


def favorite_promote(key: str) -> dict:
    return LibraryBackend().favorites_promote(key)


def favorites_list() -> list[dict]:
    return LibraryBackend().favorites_list()


def library_list() -> list[dict]:
    return LibraryBackend().library_list()


def library_get(key: str) -> dict | None:
    return LibraryBackend().library_get(key)


def library_state(stream: str, slug: str) -> dict:
    """Compact queue/library state for a single series (same shape as the
    daemon's /library/state used by the Chrome extension)."""
    if is_daemon_running():
        return daemon_client.library_state(stream, slug)
    # Fallback: reproduce the daemon's logic locally
    from streamseeker.daemon.server import _library_state
    return _library_state(stream, slug)


# ---------------------------------------------------------------------
# Live events (SSE) — only when daemon is running
# ---------------------------------------------------------------------


def events(timeout: float | None = None) -> Iterator[dict]:
    """Stream live status events from the daemon.

    Raises ``RuntimeError`` if no daemon is running, since the SSE stream
    is a daemon-only feature.
    """
    if not is_daemon_running():
        raise RuntimeError("no daemon running — start it with `streamseeker daemon start`")
    yield from daemon_client.events(timeout=timeout)


# ---------------------------------------------------------------------
# Legacy __main__ entry point
# ---------------------------------------------------------------------


if __name__ == "__main__":
    from streamseeker.api.handler import StreamseekerHandler
    from streamseeker.constants import (
        DOWNLOAD_MODE, NAME, PREF_PROVIDER, LINK_URL, LANGUAGE,
        SHOW_TYPE, SHOW_NUMBER, EPISODE_NUMBER,
    )

    logger = Logger(logging.DEBUG).instance()

    try:
        handler = StreamseekerHandler()
        handler.download(
            DOWNLOAD_MODE, NAME, PREF_PROVIDER, LINK_URL,
            LANGUAGE, SHOW_TYPE, SHOW_NUMBER, EPISODE_NUMBER,
        )
    except KeyboardInterrupt:
        logger.info(
            "----------------------------------------------------------\n"
            "--------- Downloads may still be running. ----------------\n"
            "----------------------------------------------------------\n"
            "Please don't close this terminal window until it's done.\n"
        )
    except Exception as exc:  # pragma: no cover — entry-point guard
        logger.info(
            "----------------------------------------------------------\n"
            f"Exception: {exc}\n"
            "----------------------------------------------------------\n"
        )
