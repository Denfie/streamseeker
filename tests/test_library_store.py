from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from streamseeker import paths
from streamseeker.api.core.helpers import Singleton
from streamseeker.api.core.library.store import (
    KIND_FAVORITES,
    KIND_LIBRARY,
    LibraryStore,
)


@pytest.fixture(autouse=True)
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STREAMSEEKER_HOME", str(tmp_path))
    Singleton._instances.pop(LibraryStore, None)
    yield tmp_path
    Singleton._instances.pop(LibraryStore, None)


def _entry(key="aniworldto::oshi-no-ko", **overrides) -> dict:
    base = {
        "key": key,
        "stream": key.split("::", 1)[0],
        "slug": key.split("::", 1)[1],
        "title": "Oshi No Ko",
        "year": 2023,
        "type": "staffel",
        "url": f"https://example.test/{key.split('::', 1)[1]}",
        "seasons": {"1": {"episode_count": 11, "downloaded": [1, 2]}},
    }
    base.update(overrides)
    return base


# --- basic CRUD --------------------------------------------------------


def test_add_writes_file_and_index(sandbox: Path) -> None:
    store = LibraryStore()
    stored = store.add(KIND_LIBRARY, _entry())

    file = paths.series_file(KIND_LIBRARY, "aniworldto", "oshi-no-ko")
    assert file.is_file()
    data = json.loads(file.read_text())
    assert data["title"] == "Oshi No Ko"
    assert stored["added_at"]

    index = json.loads(paths.library_index_file().read_text())
    assert len(index) == 1
    assert index[0]["key"] == "aniworldto::oshi-no-ko"
    assert index[0]["downloaded_count"] == 2
    assert index[0]["total_count"] == 11


def test_add_derives_key_from_stream_and_slug(sandbox: Path) -> None:
    store = LibraryStore()
    entry = _entry()
    del entry["key"]
    stored = store.add(KIND_LIBRARY, entry)
    assert stored["key"] == "aniworldto::oshi-no-ko"


def test_add_rejects_missing_identifiers(sandbox: Path) -> None:
    store = LibraryStore()
    with pytest.raises(ValueError):
        store.add(KIND_LIBRARY, {"title": "nope"})


def test_add_rejects_malformed_key(sandbox: Path) -> None:
    store = LibraryStore()
    with pytest.raises(ValueError):
        store.add(KIND_LIBRARY, {"key": "not-a-key"})


def test_get_returns_none_for_missing_key(sandbox: Path) -> None:
    assert LibraryStore().get(KIND_LIBRARY, "sto::does-not-exist") is None


def test_get_roundtrips_entry(sandbox: Path) -> None:
    store = LibraryStore()
    store.add(KIND_LIBRARY, _entry())
    loaded = store.get(KIND_LIBRARY, "aniworldto::oshi-no-ko")
    assert loaded is not None
    assert loaded["title"] == "Oshi No Ko"


def test_remove_deletes_file_assets_and_index(sandbox: Path) -> None:
    store = LibraryStore()
    store.add(KIND_LIBRARY, _entry())
    # Simulate asset files
    assets = paths.series_dir(KIND_LIBRARY, "aniworldto", "oshi-no-ko")
    assets.mkdir(parents=True)
    (assets / "poster.jpg").write_bytes(b"\xff\xd8\xff")

    assert store.remove(KIND_LIBRARY, "aniworldto::oshi-no-ko") is True
    assert not paths.series_file(KIND_LIBRARY, "aniworldto", "oshi-no-ko").exists()
    assert not assets.exists()
    assert json.loads(paths.library_index_file().read_text()) == []


def test_remove_returns_false_for_unknown_key(sandbox: Path) -> None:
    assert LibraryStore().remove(KIND_LIBRARY, "sto::ghost") is False


# --- upsert / merge ---------------------------------------------------


def test_add_twice_merges_downloaded_episodes(sandbox: Path) -> None:
    store = LibraryStore()
    store.add(KIND_LIBRARY, _entry(seasons={"1": {"episode_count": 11, "downloaded": [1, 2]}}))
    merged = store.add(
        KIND_LIBRARY, _entry(seasons={"1": {"episode_count": 11, "downloaded": [2, 3, 4]}})
    )
    assert merged["seasons"]["1"]["downloaded"] == [1, 2, 3, 4]


def test_add_preserves_original_added_at(sandbox: Path) -> None:
    store = LibraryStore()
    first = store.add(KIND_LIBRARY, _entry())
    original_ts = first["added_at"]
    again = store.add(KIND_LIBRARY, _entry(title="Renamed"))
    assert again["added_at"] == original_ts
    assert again["title"] == "Renamed"


def test_add_ignores_none_overrides(sandbox: Path) -> None:
    store = LibraryStore()
    store.add(KIND_LIBRARY, _entry(year=2023))
    result = store.add(KIND_LIBRARY, _entry(year=None))
    assert result["year"] == 2023


def test_mark_episode_downloaded_creates_entry_if_missing(sandbox: Path) -> None:
    store = LibraryStore()
    stored = store.mark_episode_downloaded("sto::breaking-bad", season=1, episode=3)
    assert stored["seasons"]["1"]["downloaded"] == [3]
    assert stored["title"] == "Breaking Bad"
    # index mirrors the new entry
    rows = store.list(KIND_LIBRARY)
    assert rows[0]["key"] == "sto::breaking-bad"
    assert rows[0]["downloaded_count"] == 1


def test_mark_episode_downloaded_appends_without_dupes(sandbox: Path) -> None:
    store = LibraryStore()
    store.mark_episode_downloaded("sto::breaking-bad", 1, 1)
    store.mark_episode_downloaded("sto::breaking-bad", 1, 2)
    store.mark_episode_downloaded("sto::breaking-bad", 1, 2)  # dup
    entry = store.get(KIND_LIBRARY, "sto::breaking-bad")
    assert entry["seasons"]["1"]["downloaded"] == [1, 2]


def test_mark_episode_downloaded_bumps_episode_count_when_needed(sandbox: Path) -> None:
    store = LibraryStore()
    store.add(KIND_LIBRARY, _entry(seasons={"1": {"episode_count": 5, "downloaded": []}}))
    store.mark_episode_downloaded("aniworldto::oshi-no-ko", 1, 9)
    entry = store.get(KIND_LIBRARY, "aniworldto::oshi-no-ko")
    assert entry["seasons"]["1"]["episode_count"] == 9


# --- list / search ----------------------------------------------------


def test_list_returns_index_rows(sandbox: Path) -> None:
    store = LibraryStore()
    store.add(KIND_LIBRARY, _entry("aniworldto::oshi-no-ko"))
    store.add(KIND_LIBRARY, _entry("sto::breaking-bad", title="Breaking Bad"))
    rows = store.list(KIND_LIBRARY)
    assert {r["key"] for r in rows} == {"aniworldto::oshi-no-ko", "sto::breaking-bad"}


def test_search_matches_title_and_slug_case_insensitive(sandbox: Path) -> None:
    store = LibraryStore()
    store.add(KIND_LIBRARY, _entry("aniworldto::oshi-no-ko", title="Oshi No Ko"))
    store.add(KIND_LIBRARY, _entry("sto::breaking-bad", title="Breaking Bad"))

    assert [r["key"] for r in store.search(KIND_LIBRARY, "oshi")] == [
        "aniworldto::oshi-no-ko"
    ]
    assert [r["key"] for r in store.search(KIND_LIBRARY, "BREAKING")] == [
        "sto::breaking-bad"
    ]
    # slug match
    assert [r["key"] for r in store.search(KIND_LIBRARY, "breaking-bad")] == [
        "sto::breaking-bad"
    ]


def test_search_empty_term_returns_empty(sandbox: Path) -> None:
    store = LibraryStore()
    store.add(KIND_LIBRARY, _entry())
    assert store.search(KIND_LIBRARY, "   ") == []


# --- favorites / promote ---------------------------------------------


def test_add_and_promote_favorite_to_library(sandbox: Path) -> None:
    store = LibraryStore()
    store.add(KIND_FAVORITES, _entry("aniworldto::chainsaw-man", title="Chainsaw Man"))
    # drop some asset files to verify they move
    assets = paths.series_dir(KIND_FAVORITES, "aniworldto", "chainsaw-man")
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "poster.jpg").write_bytes(b"x")

    promoted = store.move_favorite_to_library("aniworldto::chainsaw-man")
    assert promoted["title"] == "Chainsaw Man"

    # source gone
    assert not paths.series_file(KIND_FAVORITES, "aniworldto", "chainsaw-man").exists()
    assert not paths.series_dir(KIND_FAVORITES, "aniworldto", "chainsaw-man").exists()
    # destination has file and asset
    assert paths.series_file(KIND_LIBRARY, "aniworldto", "chainsaw-man").is_file()
    assert (paths.series_dir(KIND_LIBRARY, "aniworldto", "chainsaw-man") / "poster.jpg").is_file()


def test_promote_missing_favorite_raises(sandbox: Path) -> None:
    with pytest.raises(FileNotFoundError):
        LibraryStore().move_favorite_to_library("sto::ghost")


def test_promote_merges_into_existing_library_entry(sandbox: Path) -> None:
    store = LibraryStore()
    store.add(
        KIND_LIBRARY,
        _entry("sto::breaking-bad", seasons={"1": {"episode_count": 7, "downloaded": [1]}}),
    )
    store.add(
        KIND_FAVORITES,
        _entry("sto::breaking-bad", seasons={"1": {"episode_count": 7, "downloaded": [2, 3]}}),
    )
    merged = store.move_favorite_to_library("sto::breaking-bad")
    assert merged["seasons"]["1"]["downloaded"] == [1, 2, 3]


# --- index rebuild ----------------------------------------------------


def test_rebuild_index_reconstructs_from_files(sandbox: Path) -> None:
    store = LibraryStore()
    store.add(KIND_LIBRARY, _entry("aniworldto::oshi-no-ko"))
    store.add(KIND_LIBRARY, _entry("sto::breaking-bad", title="Breaking Bad"))

    # Corrupt the index
    paths.library_index_file().write_text("not json")
    assert store.list(KIND_LIBRARY) == []  # reader tolerates, returns empty

    rows = store.rebuild_index(KIND_LIBRARY)
    assert {r["key"] for r in rows} == {"aniworldto::oshi-no-ko", "sto::breaking-bad"}


# --- concurrency ------------------------------------------------------


def test_parallel_adds_serialize_via_lock(sandbox: Path) -> None:
    store = LibraryStore()
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            store.add(KIND_LIBRARY, _entry(f"sto::series-{i}", title=f"Series {i}"))
        except Exception as exc:  # pragma: no cover — should not happen
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    rows = store.list(KIND_LIBRARY)
    assert len(rows) == 20


def test_invalid_kind_raises(sandbox: Path) -> None:
    with pytest.raises(ValueError):
        LibraryStore().list("bogus")
    with pytest.raises(ValueError):
        LibraryStore().add("bogus", _entry())


# --- misc -------------------------------------------------------------


def test_external_metadata_survives_merge(sandbox: Path) -> None:
    store = LibraryStore()
    store.add(
        KIND_LIBRARY,
        _entry(external={"tmdb": {"id": 1, "poster": "poster.jpg"}}),
    )
    store.add(
        KIND_LIBRARY,
        _entry(external={"tmdb": {"rating": 8.5}, "anilist": {"id": 42}}),
    )
    entry = store.get(KIND_LIBRARY, "aniworldto::oshi-no-ko")
    assert entry["external"]["tmdb"] == {"id": 1, "poster": "poster.jpg", "rating": 8.5}
    assert entry["external"]["anilist"] == {"id": 42}


def test_library_and_favorites_are_isolated(sandbox: Path) -> None:
    store = LibraryStore()
    store.add(KIND_LIBRARY, _entry())
    assert store.list(KIND_FAVORITES) == []
    assert store.get(KIND_FAVORITES, "aniworldto::oshi-no-ko") is None
