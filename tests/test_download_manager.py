"""
Tests for DownloadManager queue operations.

The DownloadManager uses a Singleton metaclass, so each test resets the singleton
instance and redirects QUEUE_FILE to a temporary path to ensure full isolation.
"""

import json
import os
import threading
import pytest

from streamseeker.api.core.helpers import Singleton


def _reset_singleton(cls):
    """Remove a class from the Singleton registry so the next call re-initialises it."""
    Singleton._instances.pop(cls, None)


@pytest.fixture(autouse=True)
def isolated_manager(tmp_path):
    """
    Before each test:
      - Point DownloadManager.QUEUE_FILE at a temp file so no real log dir is touched.
      - Clear the singleton instance so __init__ runs fresh.

    After each test:
      - Clear the singleton again to avoid cross-test pollution.
    """
    from streamseeker.api.core.downloader.manager import DownloadManager

    queue_file = str(tmp_path / "download_queue.json")
    DownloadManager.QUEUE_FILE = queue_file
    _reset_singleton(DownloadManager)

    yield

    _reset_singleton(DownloadManager)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_manager():
    from streamseeker.api.core.downloader.manager import DownloadManager
    return DownloadManager()


def make_item(file_name="show-s1e1-de.mp4", **kwargs):
    base = {"file_name": file_name, "stream_name": "aniworldto", "name": "show"}
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Enqueue tests
# ---------------------------------------------------------------------------

def test_enqueue_adds_item():
    manager = make_manager()
    item = make_item()
    manager.enqueue(item)

    queue = manager.get_queue()
    assert len(queue) == 1
    assert queue[0]["file_name"] == "show-s1e1-de.mp4"


def test_enqueue_prevents_duplicates():
    manager = make_manager()
    item = make_item()
    manager.enqueue(item)
    manager.enqueue(item)  # duplicate

    queue = manager.get_queue()
    assert len(queue) == 1


def test_enqueue_sets_defaults():
    manager = make_manager()
    manager.enqueue({"file_name": "test.mp4"})

    queue = manager.get_queue()
    entry = queue[0]
    assert entry["status"] == "pending"
    assert entry["attempts"] == 0
    assert entry["skip_reason"] is None
    assert entry["last_error"] is None


# ---------------------------------------------------------------------------
# mark_status tests
# ---------------------------------------------------------------------------

def test_mark_status_updates_item():
    manager = make_manager()
    manager.enqueue(make_item("ep1.mp4"))
    manager.mark_status("ep1.mp4", "downloading")

    entry = manager.get_queue()[0]
    assert entry["status"] == "downloading"


def test_mark_status_with_kwargs():
    manager = make_manager()
    manager.enqueue(make_item("ep2.mp4"))
    manager.mark_status("ep2.mp4", "skipped", skip_reason="no language")

    entry = manager.get_queue()[0]
    assert entry["status"] == "skipped"
    assert entry["skip_reason"] == "no language"


def test_mark_status_nonexistent_item():
    manager = make_manager()
    # Should not raise even if file_name not in queue
    manager.mark_status("ghost.mp4", "failed")


# ---------------------------------------------------------------------------
# get_next_pending tests
# ---------------------------------------------------------------------------

def test_get_next_pending_returns_pending_first():
    manager = make_manager()
    manager.enqueue(make_item("failed.mp4", status="failed"))
    manager.mark_status("failed.mp4", "failed")  # ensure persisted
    manager.enqueue(make_item("pending.mp4"))

    next_item = manager.get_next_pending()
    assert next_item is not None
    assert next_item["file_name"] == "pending.mp4"


def test_get_next_pending_returns_failed_if_no_pending():
    manager = make_manager()
    manager.enqueue(make_item("only-failed.mp4"))
    manager.mark_status("only-failed.mp4", "failed")

    next_item = manager.get_next_pending()
    assert next_item is not None
    assert next_item["file_name"] == "only-failed.mp4"


def test_get_next_pending_returns_none_for_empty():
    manager = make_manager()
    assert manager.get_next_pending() is None


def test_get_next_pending_skips_downloading():
    manager = make_manager()
    manager.enqueue(make_item("busy.mp4"))
    manager.mark_status("busy.mp4", "downloading")
    manager.enqueue(make_item("ready.mp4"))

    next_item = manager.get_next_pending()
    assert next_item is not None
    assert next_item["file_name"] == "ready.mp4"


# ---------------------------------------------------------------------------
# queue_summary tests
# ---------------------------------------------------------------------------

def test_queue_summary_counts():
    manager = make_manager()
    manager.enqueue(make_item("p1.mp4"))
    manager.enqueue(make_item("p2.mp4"))
    manager.enqueue(make_item("f1.mp4"))
    manager.mark_status("f1.mp4", "failed")
    manager.enqueue(make_item("s1.mp4"))
    manager.mark_status("s1.mp4", "skipped")

    summary = manager.queue_summary()
    assert summary["pending"] == 2
    assert summary["failed"] == 1
    assert summary["skipped"] == 1
    assert summary["downloading"] == 0


# ---------------------------------------------------------------------------
# report_success tests
# ---------------------------------------------------------------------------

def test_report_success_removes_from_queue():
    manager = make_manager()
    manager.enqueue(make_item("done.mp4"))
    assert len(manager.get_queue()) == 1

    manager.report_success("done.mp4")
    assert len(manager.get_queue()) == 0


# ---------------------------------------------------------------------------
# get_pending_items tests
# ---------------------------------------------------------------------------

def test_get_pending_items():
    manager = make_manager()
    manager.enqueue(make_item("a.mp4"))                     # pending
    manager.enqueue(make_item("b.mp4"))
    manager.mark_status("b.mp4", "failed")                 # failed
    manager.enqueue(make_item("c.mp4"))
    manager.mark_status("c.mp4", "skipped")               # skipped
    manager.enqueue(make_item("d.mp4"))
    manager.mark_status("d.mp4", "downloading")            # downloading

    pending = manager.get_pending_items()
    file_names = {item["file_name"] for item in pending}
    assert "a.mp4" in file_names
    assert "b.mp4" in file_names
    assert "c.mp4" not in file_names
    assert "d.mp4" not in file_names


# ---------------------------------------------------------------------------
# Persistence test
# ---------------------------------------------------------------------------

def test_queue_persistence(tmp_path):
    """
    Enqueue items via one manager instance, then create a fresh singleton and
    verify the queue data is still there (loaded from the JSON file).
    """
    from streamseeker.api.core.downloader.manager import DownloadManager

    queue_file = str(tmp_path / "persist_queue.json")
    DownloadManager.QUEUE_FILE = queue_file
    _reset_singleton(DownloadManager)

    m1 = DownloadManager()
    m1.enqueue(make_item("persist.mp4"))

    # Destroy the singleton so a new instance is created from scratch
    _reset_singleton(DownloadManager)
    DownloadManager.QUEUE_FILE = queue_file  # keep same file

    m2 = DownloadManager()
    queue = m2.get_queue()
    assert len(queue) == 1
    assert queue[0]["file_name"] == "persist.mp4"
