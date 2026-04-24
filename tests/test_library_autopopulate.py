"""Paket B — auto-population of the Library from successful downloads.

Verifies that ``DownloadManager.report_success`` threads the queue item into
``LibraryStore`` without blocking the downloader on failure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from streamseeker.api.core.downloader.manager import DownloadManager
from streamseeker.api.core.helpers import Singleton
from streamseeker.api.core.library import LibraryStore
from streamseeker.api.core.library.store import KIND_LIBRARY


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STREAMSEEKER_HOME", str(tmp_path))
    Singleton._instances.pop(DownloadManager, None)
    Singleton._instances.pop(LibraryStore, None)
    yield
    Singleton._instances.pop(DownloadManager, None)
    Singleton._instances.pop(LibraryStore, None)


def _enqueue_episode(manager: DownloadManager, file_name: str = "a.mp4",
                     *, stream="sto", slug="breaking-bad", season=1, episode=3,
                     type_="staffel") -> None:
    manager.enqueue({
        "file_name": file_name,
        "stream_name": stream,
        "name": slug,
        "type": type_,
        "season": season,
        "episode": episode,
    })


def test_report_success_records_episode_in_library() -> None:
    manager = DownloadManager()
    _enqueue_episode(manager, "bb-s1e3.mp4", season=1, episode=3)

    manager.report_success("bb-s1e3.mp4")

    entry = LibraryStore().get(KIND_LIBRARY, "sto::breaking-bad")
    assert entry is not None
    assert entry["seasons"]["1"]["downloaded"] == [3]


def test_report_success_accumulates_multiple_episodes() -> None:
    manager = DownloadManager()
    _enqueue_episode(manager, "bb-s1e1.mp4", episode=1)
    _enqueue_episode(manager, "bb-s1e2.mp4", episode=2)
    manager.report_success("bb-s1e1.mp4")
    manager.report_success("bb-s1e2.mp4")

    entry = LibraryStore().get(KIND_LIBRARY, "sto::breaking-bad")
    assert entry["seasons"]["1"]["downloaded"] == [1, 2]


def test_report_success_removes_item_from_queue() -> None:
    manager = DownloadManager()
    _enqueue_episode(manager, "bb-s1e1.mp4", episode=1)
    manager.report_success("bb-s1e1.mp4")
    assert manager.get_queue() == []


def test_report_success_handles_movie_type() -> None:
    manager = DownloadManager()
    _enqueue_episode(
        manager, "dune.mp4",
        stream="megakinotax", slug="dune-part-two",
        season=0, episode=1, type_="filme",
    )
    manager.report_success("dune.mp4")

    entry = LibraryStore().get(KIND_LIBRARY, "megakinotax::dune-part-two")
    assert entry is not None
    assert entry["movies"]["downloaded"] == [1]
    assert entry["seasons"] == {}


def test_report_success_without_matching_item_is_noop() -> None:
    manager = DownloadManager()
    # Nothing queued — should not raise and library stays empty
    manager.report_success("nonexistent.mp4")
    assert LibraryStore().list(KIND_LIBRARY) == []


def test_report_success_skips_library_write_for_malformed_item() -> None:
    """An item missing stream/slug must not crash the success path."""
    manager = DownloadManager()
    manager.enqueue({"file_name": "bad.mp4", "season": 1, "episode": 1})
    manager.report_success("bad.mp4")  # must not raise
    assert LibraryStore().list(KIND_LIBRARY) == []


def test_report_success_skips_library_write_when_season_is_zero() -> None:
    """Queue items for series require season>0 and episode>0 to count."""
    manager = DownloadManager()
    _enqueue_episode(manager, "weird.mp4", season=0, episode=0)
    manager.report_success("weird.mp4")
    assert LibraryStore().list(KIND_LIBRARY) == []


def test_report_success_survives_library_write_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """If LibraryStore blows up, report_success must still remove from queue."""
    manager = DownloadManager()
    _enqueue_episode(manager, "bb-s1e1.mp4", episode=1)

    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated store failure")

    monkeypatch.setattr(LibraryStore, "mark_episode_downloaded", boom)

    # Must not raise
    manager.report_success("bb-s1e1.mp4")

    # Queue still cleared
    assert manager.get_queue() == []


def test_library_index_reflects_autopopulated_entry() -> None:
    manager = DownloadManager()
    _enqueue_episode(manager, "bb-s1e1.mp4", episode=1)
    manager.report_success("bb-s1e1.mp4")

    rows = LibraryStore().list(KIND_LIBRARY)
    assert len(rows) == 1
    assert rows[0]["downloaded_count"] == 1
    assert rows[0]["key"] == "sto::breaking-bad"
