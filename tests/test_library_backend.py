"""Paket E — LibraryBackend facade chooses between local store and daemon."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from streamseeker.api.core import daemon_client
from streamseeker.api.core.helpers import Singleton
from streamseeker.api.core.library import LibraryStore
from streamseeker.api.core.library_backend import LibraryBackend


@pytest.fixture(autouse=True)
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STREAMSEEKER_HOME", str(tmp_path))
    Singleton._instances.pop(LibraryStore, None)
    yield
    Singleton._instances.pop(LibraryStore, None)


# --- local-only path (no daemon) -------------------------------------


def test_local_favorites_add_writes_through_store() -> None:
    backend = LibraryBackend(prefer_daemon=False)
    entry = backend.favorites_add("sto", "breaking-bad")
    assert entry["key"] == "sto::breaking-bad"
    # directly reading the store should see it
    assert LibraryStore().get("favorites", "sto::breaking-bad") is not None


def test_local_favorites_list_reads_store() -> None:
    LibraryStore().add("favorites", {"stream": "sto", "slug": "breaking-bad"})
    backend = LibraryBackend(prefer_daemon=False)
    rows = backend.favorites_list()
    assert len(rows) == 1
    assert rows[0]["key"] == "sto::breaking-bad"


def test_local_favorites_remove() -> None:
    LibraryStore().add("favorites", {"stream": "sto", "slug": "breaking-bad"})
    backend = LibraryBackend(prefer_daemon=False)
    assert backend.favorites_remove("sto::breaking-bad") is True
    assert backend.favorites_remove("sto::breaking-bad") is False


def test_local_library_get_and_search() -> None:
    LibraryStore().mark_episode_downloaded("sto::breaking-bad", 1, 1)
    backend = LibraryBackend(prefer_daemon=False)
    assert backend.library_get("sto::breaking-bad") is not None
    rows = backend.library_search("breaking")
    assert len(rows) == 1


def test_local_library_search_empty_term() -> None:
    backend = LibraryBackend(prefer_daemon=False)
    assert backend.library_search("   ") == []


def test_local_favorites_promote() -> None:
    LibraryStore().add("favorites", {"stream": "sto", "slug": "breaking-bad"})
    backend = LibraryBackend(prefer_daemon=False)
    promoted = backend.favorites_promote("sto::breaking-bad")
    assert promoted["key"] == "sto::breaking-bad"


# --- daemon path (mocked) -------------------------------------------


def test_daemon_favorites_add_uses_http() -> None:
    with patch.object(daemon_client, "is_daemon_running", return_value=True), \
         patch.object(daemon_client, "favorites_add", return_value={"key": "sto::x", "title": "X"}) as mock_add:
        backend = LibraryBackend()
        result = backend.favorites_add("sto", "x")
        mock_add.assert_called_once_with("sto", "x")
        assert result["title"] == "X"


def test_daemon_favorites_remove_returns_false_on_404() -> None:
    err = daemon_client.DaemonError(404, "not found")
    with patch.object(daemon_client, "is_daemon_running", return_value=True), \
         patch.object(daemon_client, "favorites_remove", side_effect=err):
        backend = LibraryBackend()
        assert backend.favorites_remove("sto::ghost") is False


def test_daemon_favorites_remove_propagates_non_404() -> None:
    err = daemon_client.DaemonError(500, "boom")
    with patch.object(daemon_client, "is_daemon_running", return_value=True), \
         patch.object(daemon_client, "favorites_remove", side_effect=err):
        backend = LibraryBackend()
        with pytest.raises(daemon_client.DaemonError):
            backend.favorites_remove("sto::x")


def test_daemon_library_list_falls_back_to_local_on_error() -> None:
    LibraryStore().mark_episode_downloaded("sto::breaking-bad", 1, 1)
    with patch.object(daemon_client, "is_daemon_running", return_value=True), \
         patch.object(daemon_client, "library_list", side_effect=RuntimeError("unreachable")):
        backend = LibraryBackend()
        rows = backend.library_list()
        assert len(rows) == 1
        assert rows[0]["key"] == "sto::breaking-bad"


def test_daemon_library_get_returns_none_on_404() -> None:
    err = daemon_client.DaemonError(404, "not found")
    with patch.object(daemon_client, "is_daemon_running", return_value=True), \
         patch.object(daemon_client, "library_get", side_effect=err):
        backend = LibraryBackend()
        # Will also try local store as fallback; it's empty, so None is expected
        assert backend.library_get("sto::ghost") is None


def test_daemon_library_get_falls_back_to_local_on_other_error() -> None:
    LibraryStore().mark_episode_downloaded("sto::breaking-bad", 1, 1)
    err = daemon_client.DaemonError(500, "boom")
    with patch.object(daemon_client, "is_daemon_running", return_value=True), \
         patch.object(daemon_client, "library_get", side_effect=err):
        backend = LibraryBackend()
        entry = backend.library_get("sto::breaking-bad")
        # Fell back to local store
        assert entry is not None
        assert entry["key"] == "sto::breaking-bad"


# --- uses_daemon flag -----------------------------------------------


def test_uses_daemon_reflects_runtime_state() -> None:
    with patch.object(daemon_client, "is_daemon_running", return_value=True):
        assert LibraryBackend().uses_daemon is True
    with patch.object(daemon_client, "is_daemon_running", return_value=False):
        assert LibraryBackend().uses_daemon is False


def test_prefer_daemon_override_wins() -> None:
    with patch.object(daemon_client, "is_daemon_running", return_value=True):
        assert LibraryBackend(prefer_daemon=False).uses_daemon is False
