"""Tests for the update-detection pipeline (new seasons/episodes/movies)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from streamseeker.api.core.downloader.manager import DownloadManager
from streamseeker.api.core.helpers import Singleton
from streamseeker.api.core.library import LibraryStore
from streamseeker.api.core.library.store import KIND_LIBRARY
from streamseeker.api.core.library.updates import (
    CheckResult,
    build_signature,
    check_entry,
    collect_pending,
    diff_signatures,
    dismiss_updates,
)
from streamseeker.daemon.server import create_app


@pytest.fixture(autouse=True)
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STREAMSEEKER_HOME", str(tmp_path))
    Singleton._instances.pop(DownloadManager, None)
    Singleton._instances.pop(LibraryStore, None)
    yield
    Singleton._instances.pop(DownloadManager, None)
    Singleton._instances.pop(LibraryStore, None)


# --- diff_signatures --------------------------------------------------


def test_diff_signatures_ignores_initial_discovery() -> None:
    new = {"seasons": {"1": 12}, "movies": 0}
    assert diff_signatures(None, new) == []


def test_diff_signatures_flags_new_season() -> None:
    old = {"seasons": {"1": 12, "2": 13}, "movies": 0}
    new = {"seasons": {"1": 12, "2": 13, "3": 11}, "movies": 0}
    updates = diff_signatures(old, new)
    assert len(updates) == 1
    assert updates[0]["type"] == "new_season"
    assert updates[0]["season"] == 3


def test_diff_signatures_flags_new_episode_in_existing_season() -> None:
    old = {"seasons": {"3": 11}, "movies": 0}
    new = {"seasons": {"3": 12}, "movies": 0}
    updates = diff_signatures(old, new)
    assert len(updates) == 1
    assert updates[0]["type"] == "new_episode"
    assert updates[0]["season"] == 3
    assert updates[0]["from"] == 11
    assert updates[0]["to"] == 12


def test_diff_signatures_flags_new_movie() -> None:
    old = {"seasons": {}, "movies": 2}
    new = {"seasons": {}, "movies": 3}
    updates = diff_signatures(old, new)
    assert len(updates) == 1
    assert updates[0]["type"] == "new_movie"
    assert updates[0]["count_after"] == 3


def test_diff_signatures_reports_multiple_changes() -> None:
    old = {"seasons": {"1": 10}, "movies": 0}
    new = {"seasons": {"1": 11, "2": 12}, "movies": 1}
    updates = diff_signatures(old, new)
    kinds = sorted(u["type"] for u in updates)
    assert kinds == ["new_episode", "new_movie", "new_season"]


def test_diff_signatures_ignores_shrinking_counts() -> None:
    # Stream temporarily loses an episode — we don't cry about it.
    old = {"seasons": {"1": 12}, "movies": 3}
    new = {"seasons": {"1": 11}, "movies": 2}
    assert diff_signatures(old, new) == []


# --- build_signature -------------------------------------------------


def test_build_signature_uses_series_list_from_search() -> None:
    handler = MagicMock()
    handler.search.return_value = {"types": ["staffel"], "series": [1, 2], "movies": []}
    handler.search_episodes.side_effect = lambda *_args, **_kw: [1, 2, 3]

    sig = build_signature(handler, "aniworldto", "x")
    assert sig == {"seasons": {"1": 3, "2": 3}, "movies": 0}


def test_build_signature_handles_movie_type() -> None:
    handler = MagicMock()
    handler.search.return_value = {"types": ["filme"], "series": [], "movies": [1, 2]}

    sig = build_signature(handler, "megakinotax", "x")
    assert sig == {"seasons": {}, "movies": 2}


# --- check_entry ------------------------------------------------------


def _library_entry(store: LibraryStore, stream: str, slug: str, **extra):
    entry = {"stream": stream, "slug": slug, **extra}
    store.add(KIND_LIBRARY, entry)
    return store.get(KIND_LIBRARY, f"{stream}::{slug}")


def test_check_entry_stores_initial_signature_without_flagging() -> None:
    store = LibraryStore()
    _library_entry(store, "aniworldto", "new-show")

    handler = MagicMock()
    handler.search.return_value = {"types": ["staffel"], "series": [1], "movies": []}
    handler.search_episodes.return_value = [1, 2, 3]

    result = check_entry(handler, store, KIND_LIBRARY, "aniworldto::new-show")
    assert result.changed is False
    assert result.updates_added == 0

    entry = store.get(KIND_LIBRARY, "aniworldto::new-show") or {}
    assert entry.get("content_signature") == {"seasons": {"1": 3}, "movies": 0}
    assert entry.get("last_checked")
    assert entry.get("pending_updates") == []


def test_check_entry_flags_changes_against_previous_signature() -> None:
    store = LibraryStore()
    store.add(KIND_LIBRARY, {
        "stream": "aniworldto", "slug": "oshi",
        "content_signature": {"seasons": {"1": 3}, "movies": 0},
    })

    handler = MagicMock()
    handler.search.return_value = {"types": ["staffel"], "series": [1, 2], "movies": []}
    handler.search_episodes.side_effect = lambda *_a, **_k: [1, 2, 3, 4] if _a[3] == 2 else [1, 2, 3]

    result = check_entry(handler, store, KIND_LIBRARY, "aniworldto::oshi")
    assert result.changed is True
    # S2 is new → 1 update. S1 unchanged.
    assert result.updates_added == 1

    entry = store.get(KIND_LIBRARY, "aniworldto::oshi") or {}
    assert any(u["type"] == "new_season" for u in entry.get("pending_updates", []))


# --- dismiss + collect -----------------------------------------------


def test_dismiss_updates_clears_the_list() -> None:
    store = LibraryStore()
    store.add(KIND_LIBRARY, {
        "stream": "aniworldto", "slug": "x",
        "pending_updates": [{"type": "new_season", "season": 2}],
    })
    assert dismiss_updates(store, KIND_LIBRARY, "aniworldto::x") is True
    assert store.get(KIND_LIBRARY, "aniworldto::x")["pending_updates"] == []


def test_dismiss_updates_returns_false_for_unknown_key() -> None:
    store = LibraryStore()
    assert dismiss_updates(store, KIND_LIBRARY, "aniworldto::ghost") is False


def test_dismiss_all_updates_clears_every_entry() -> None:
    from streamseeker.api.core.library.updates import dismiss_all_updates

    store = LibraryStore()
    store.add(KIND_LIBRARY, {
        "stream": "aniworldto", "slug": "a",
        "pending_updates": [{"type": "new_season", "season": 2}],
    })
    store.add(KIND_LIBRARY, {
        "stream": "sto", "slug": "b",
        "pending_updates": [{"type": "new_episode", "season": 1, "from": 3, "to": 4}],
    })
    store.add(KIND_LIBRARY, {
        "stream": "sto", "slug": "c",  # no pending_updates → must not be touched
    })

    cleared = dismiss_all_updates(store, KIND_LIBRARY)
    assert cleared == 2
    assert store.get(KIND_LIBRARY, "aniworldto::a")["pending_updates"] == []
    assert store.get(KIND_LIBRARY, "sto::b")["pending_updates"] == []


def test_dismiss_all_updates_idempotent_on_empty_state() -> None:
    from streamseeker.api.core.library.updates import dismiss_all_updates

    store = LibraryStore()
    store.add(KIND_LIBRARY, {"stream": "aniworldto", "slug": "x"})
    assert dismiss_all_updates(store, KIND_LIBRARY) == 0


def test_collect_pending_reports_favorite_flag() -> None:
    store = LibraryStore()
    store.add(KIND_LIBRARY, {
        "stream": "aniworldto", "slug": "a",
        "pending_updates": [{"type": "new_episode", "season": 1, "from": 3, "to": 4}],
    })
    store.add(KIND_LIBRARY, {
        "stream": "sto", "slug": "b",
    })  # tracked but no updates → should not appear
    store.add(KIND_LIBRARY, {
        "stream": "sto", "slug": "c",
        "favorite": True,
        "pending_updates": [{"type": "new_season", "season": 2}],
    })

    rows = collect_pending(store)
    keys = {r["key"] for r in rows}
    assert keys == {"aniworldto::a", "sto::c"}

    fav_row = next(r for r in rows if r["key"] == "sto::c")
    assert fav_row["favorite"] is True
    plain_row = next(r for r in rows if r["key"] == "aniworldto::a")
    assert plain_row["favorite"] is False


# --- HTTP endpoints --------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_get_updates_returns_pending_entries(client: TestClient) -> None:
    LibraryStore().add(KIND_LIBRARY, {
        "stream": "aniworldto", "slug": "oshi-no-ko",
        "title": "Oshi No Ko",
        "pending_updates": [{"type": "new_season", "season": 4, "detected_at": "2026-04-24T00:00:00+00:00"}],
    })
    response = client.get("/updates")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["key"] == "aniworldto::oshi-no-ko"
    assert body[0]["pending_updates"][0]["type"] == "new_season"


def test_dismiss_endpoint_clears_pending(client: TestClient) -> None:
    LibraryStore().add(KIND_LIBRARY, {
        "stream": "aniworldto", "slug": "x",
        "pending_updates": [{"type": "new_season", "season": 2}],
    })
    assert client.get("/updates").json()
    response = client.post("/updates/aniworldto::x/dismiss")
    assert response.status_code == 200
    assert response.json()["dismissed"] is True
    assert client.get("/updates").json() == []


def test_dismiss_unknown_key_returns_404(client: TestClient) -> None:
    assert client.post("/updates/aniworldto::ghost/dismiss").status_code == 404


def test_dismiss_all_endpoint_clears_every_pending(client: TestClient) -> None:
    LibraryStore().add(KIND_LIBRARY, {
        "stream": "aniworldto", "slug": "a",
        "pending_updates": [{"type": "new_season", "season": 2}],
    })
    LibraryStore().add(KIND_LIBRARY, {
        "stream": "sto", "slug": "b",
        "pending_updates": [{"type": "new_episode", "season": 1, "from": 3, "to": 4}],
    })
    assert len(client.get("/updates").json()) == 2

    response = client.post("/updates/dismiss-all")
    assert response.status_code == 200
    assert response.json() == {"dismissed": 2}
    assert client.get("/updates").json() == []


def test_dismiss_all_endpoint_idempotent_when_nothing_pending(client: TestClient) -> None:
    LibraryStore().add(KIND_LIBRARY, {"stream": "aniworldto", "slug": "x"})
    response = client.post("/updates/dismiss-all")
    assert response.status_code == 200
    assert response.json() == {"dismissed": 0}
