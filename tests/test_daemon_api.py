"""Paket D.3 — HTTP endpoints of the FastAPI daemon."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from streamseeker.api.core.downloader.manager import DownloadManager
from streamseeker.api.core.helpers import Singleton
from streamseeker.api.core.library import LibraryStore
from streamseeker.daemon.server import create_app


@pytest.fixture(autouse=True)
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STREAMSEEKER_HOME", str(tmp_path))
    Singleton._instances.pop(DownloadManager, None)
    Singleton._instances.pop(LibraryStore, None)
    # Library-state cache is process-global; wipe between tests so the
    # previous test's tmp_path state can't leak into this one.
    from streamseeker.daemon import server as _server
    _server._invalidate_library_state_cache()
    yield
    Singleton._instances.pop(DownloadManager, None)
    Singleton._instances.pop(LibraryStore, None)
    _server._invalidate_library_state_cache()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


# --- meta --------------------------------------------------------------


def test_version_returns_cli_version(client: TestClient) -> None:
    response = client.get("/version")
    assert response.status_code == 200
    body = response.json()
    assert "cli" in body
    assert body["cli"]


def test_status_returns_summary_and_progress(client: TestClient) -> None:
    response = client.get("/status")
    assert response.status_code == 200
    body = response.json()
    assert "summary" in body
    assert "progress" in body
    assert "timestamp" in body
    assert body["summary"]["pending"] == 0


def test_dashboard_returns_html(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "StreamSeeker" in response.text


# --- queue -------------------------------------------------------------


def test_queue_list_starts_empty(client: TestClient) -> None:
    assert client.get("/queue").json() == []


def test_queue_add_enqueues_item(client: TestClient) -> None:
    response = client.post(
        "/queue",
        json={"stream": "sto", "slug": "breaking-bad", "season": 1, "episode": 1, "type": "staffel"},
    )
    assert response.status_code == 201
    assert response.json()["enqueued"] is True

    queue = client.get("/queue").json()
    assert len(queue) == 1
    assert queue[0]["stream_name"] == "sto"
    assert queue[0]["name"] == "breaking-bad"
    assert queue[0]["season"] == 1


def test_queue_add_rejects_malformed_body(client: TestClient) -> None:
    # Missing required 'stream'/'slug'
    response = client.post("/queue", json={"type": "staffel"})
    assert response.status_code == 422


# --- library -----------------------------------------------------------


def test_library_list_starts_empty(client: TestClient) -> None:
    assert client.get("/library").json() == []


def test_library_list_reflects_store_state(client: TestClient) -> None:
    LibraryStore().mark_episode_downloaded("sto::breaking-bad", 1, 1)
    body = client.get("/library").json()
    assert len(body) == 1
    assert body[0]["key"] == "sto::breaking-bad"
    assert body[0]["downloaded_count"] == 1


def test_library_get_returns_404_for_unknown_key(client: TestClient) -> None:
    response = client.get("/library/sto::does-not-exist")
    assert response.status_code == 404


def test_library_get_returns_entry(client: TestClient) -> None:
    LibraryStore().mark_episode_downloaded("sto::breaking-bad", 1, 1)
    response = client.get("/library/sto::breaking-bad")
    assert response.status_code == 200
    entry = response.json()
    assert entry["key"] == "sto::breaking-bad"
    assert entry["seasons"]["1"]["downloaded"] == [1]


# --- library state ----------------------------------------------------


def test_library_state_unknown_series_returns_empty_state(client: TestClient) -> None:
    response = client.get("/library/state", params={"stream": "sto", "slug": "ghost"})
    assert response.status_code == 200
    body = response.json()
    assert body["favorite"] is False
    assert body["library"] is False
    assert body["seasons"] == {}


def test_library_state_reflects_favorite_and_library_and_queue(client: TestClient) -> None:
    store = LibraryStore()
    store.set_favorite("sto::breaking-bad", True)
    store.mark_episode_downloaded("sto::breaking-bad", 1, 1)
    store.mark_episode_downloaded("sto::breaking-bad", 1, 2)

    # Enqueue one pending + one failed item to populate the queued/failed counts
    manager = DownloadManager()
    manager.enqueue({
        "file_name": "q1.mp4", "stream_name": "sto", "name": "breaking-bad",
        "season": 1, "episode": 3, "type": "staffel",
    })
    manager.enqueue({
        "file_name": "q2.mp4", "stream_name": "sto", "name": "breaking-bad",
        "season": 2, "episode": 1, "type": "staffel",
    })
    manager.mark_status("q2.mp4", "failed")

    response = client.get("/library/state", params={"stream": "sto", "slug": "breaking-bad"})
    body = response.json()

    assert body["favorite"] is True
    assert body["library"] is True
    assert body["seasons"]["1"]["downloaded"] == 2
    # `pending` items count as "skipped" — "queued" is reserved for
    # actively downloading items.
    assert body["seasons"]["1"]["skipped"] == 1
    assert body["seasons"]["2"]["failed"] == 1


def test_library_state_includes_per_episode_status(client: TestClient) -> None:
    """Content-scripts need to colour individual episode links; state must
    carry a per-episode map, not just aggregates."""
    store = LibraryStore()
    store.mark_episode_downloaded("sto::breaking-bad", 1, 1)
    store.mark_episode_downloaded("sto::breaking-bad", 1, 2)

    manager = DownloadManager()
    manager.enqueue({
        "file_name": "q-pending.mp4", "stream_name": "sto", "name": "breaking-bad",
        "season": 1, "episode": 3, "type": "staffel",
    })
    manager.enqueue({
        "file_name": "q-failed.mp4", "stream_name": "sto", "name": "breaking-bad",
        "season": 1, "episode": 4, "type": "staffel",
    })
    manager.mark_status("q-failed.mp4", "failed")

    body = client.get(
        "/library/state", params={"stream": "sto", "slug": "breaking-bad"},
    ).json()

    eps = body["seasons"]["1"]["episodes"]
    assert eps["1"] == "downloaded"
    assert eps["2"] == "downloaded"
    # Pending queue items show as "skipped" (waiting); only an actively
    # downloading item would be "queued" on the page.
    assert eps["3"] == "skipped"
    assert eps["4"] == "failed"


def test_library_state_failed_does_not_overwrite_downloaded(client: TestClient) -> None:
    """A later failed re-attempt on an already-downloaded episode must not
    demote its per-episode status."""
    store = LibraryStore()
    store.mark_episode_downloaded("sto::breaking-bad", 1, 1)

    manager = DownloadManager()
    manager.enqueue({
        "file_name": "q-retry.mp4", "stream_name": "sto", "name": "breaking-bad",
        "season": 1, "episode": 1, "type": "staffel",
    })
    manager.mark_status("q-retry.mp4", "failed")

    body = client.get(
        "/library/state", params={"stream": "sto", "slug": "breaking-bad"},
    ).json()
    assert body["seasons"]["1"]["episodes"]["1"] == "downloaded"


# --- favorites --------------------------------------------------------


def test_favorites_empty_by_default(client: TestClient) -> None:
    assert client.get("/favorites").json() == []


def test_favorites_add_creates_entry(client: TestClient) -> None:
    response = client.post("/favorites", json={"stream": "aniworldto", "slug": "oshi-no-ko"})
    assert response.status_code == 201
    entry = response.json()
    assert entry["key"] == "aniworldto::oshi-no-ko"

    rows = client.get("/favorites").json()
    assert len(rows) == 1


def test_favorites_add_rejects_missing_fields(client: TestClient) -> None:
    response = client.post("/favorites", json={"stream": "aniworldto"})
    assert response.status_code == 422


def test_favorites_delete_removes_entry(client: TestClient) -> None:
    client.post("/favorites", json={"stream": "sto", "slug": "breaking-bad"})
    response = client.delete("/favorites/sto::breaking-bad")
    assert response.status_code == 200
    assert response.json()["removed"] is True
    assert client.get("/favorites").json() == []


def test_favorites_delete_unknown_is_404(client: TestClient) -> None:
    response = client.delete("/favorites/sto::ghost")
    assert response.status_code == 404


def test_favorites_promote_is_noop_with_merged_collection(client: TestClient) -> None:
    """Favorites live in the library now. ``/promote`` keeps working for
    back-compat but no longer moves anything — the entry already IS in the
    library, just with ``favorite: true``."""
    client.post("/favorites", json={"stream": "aniworldto", "slug": "chainsaw-man"})
    response = client.post("/favorites/aniworldto::chainsaw-man/promote")
    assert response.status_code == 200
    entry = response.json()
    assert entry["key"] == "aniworldto::chainsaw-man"
    assert entry["favorite"] is True

    # Library lists the same entry.
    library_rows = client.get("/library").json()
    assert any(r["key"] == "aniworldto::chainsaw-man" for r in library_rows)


def test_favorites_promote_unknown_is_404(client: TestClient) -> None:
    response = client.post("/favorites/sto::ghost/promote")
    assert response.status_code == 404


# --- SSE --------------------------------------------------------------
#
# The /events endpoint is a long-running SSE stream. FastAPI's TestClient
# blocks until the server closes, so we verify the building blocks directly
# (status payload + route registration) instead of consuming the live stream.
# Real browser behavior is covered by the extension's integration tests in F.


def test_events_route_is_registered() -> None:
    from streamseeker.daemon.server import create_app

    app = create_app()
    paths_registered = {r.path for r in app.routes}
    assert "/events" in paths_registered


def test_build_status_payload_is_json_serializable() -> None:
    from streamseeker.daemon.server import _build_status

    payload = _build_status()
    # Sanity: keys present, JSON-serializable
    assert {"summary", "progress", "timestamp"} <= payload.keys()
    import json as _json
    _json.dumps(payload)


# --- CORS -------------------------------------------------------------


def test_cors_allows_chrome_extension_origin(client: TestClient) -> None:
    response = client.get(
        "/status",
        headers={"Origin": "chrome-extension://abcdef1234567890"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "chrome-extension://abcdef1234567890"


@pytest.mark.parametrize("origin", [
    "https://aniworld.to",
    "https://s.to",
    "https://megakino.tax",
])
def test_cors_allows_stream_host_origins(client: TestClient, origin: str) -> None:
    """Manifest V3 content-scripts fetch with the host-page origin."""
    response = client.get("/status", headers={"Origin": origin})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin


def test_cors_rejects_arbitrary_origin(client: TestClient) -> None:
    response = client.get("/status", headers={"Origin": "https://evil.example"})
    assert response.status_code == 200
    # Middleware simply omits the header for disallowed origins → browser blocks.
    assert response.headers.get("access-control-allow-origin") is None
