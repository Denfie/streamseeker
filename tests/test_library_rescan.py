"""Tests for rebuilding Library entries from a migrated success.log."""

from __future__ import annotations

from pathlib import Path

import pytest

from streamseeker import paths
from streamseeker.api.core.helpers import Singleton
from streamseeker.api.core.library import LibraryStore
from streamseeker.api.core.library.rescan import (
    RescanItem,
    classify_path,
    rescan_success_log,
)
from streamseeker.api.core.library.store import KIND_LIBRARY


@pytest.fixture(autouse=True)
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STREAMSEEKER_HOME", str(tmp_path))
    Singleton._instances.pop(LibraryStore, None)
    yield
    Singleton._instances.pop(LibraryStore, None)


# --- classify_path -----------------------------------------------------


def test_classify_aniworldto_staffel() -> None:
    item = classify_path("downloads/anime/oshi-no-ko/Season 1/oshi-no-ko-s1e3-german.mp4")
    assert item == RescanItem("aniworldto", "oshi-no-ko", "staffel", 1, 3)


def test_classify_sto_staffel() -> None:
    item = classify_path("downloads/serie/breaking-bad/Season 2/breaking-bad-s2e5-german.mp4")
    assert item == RescanItem("sto", "breaking-bad", "staffel", 2, 5)


def test_classify_aniworldto_filme() -> None:
    item = classify_path("downloads/anime/some-anime/movies/some-anime-movie-1-german.mp4")
    assert item == RescanItem("aniworldto", "some-anime", "filme", season=0, episode=1)


def test_classify_with_absolute_path() -> None:
    item = classify_path("/Users/me/.streamseeker/downloads/anime/foo/Season 1/foo-s1e1-de.mp4")
    assert item == RescanItem("aniworldto", "foo", "staffel", 1, 1)


def test_classify_unknown_layout_returns_none() -> None:
    assert classify_path("downloads/random/bar/baz.mp4") is None


def test_classify_ignores_malformed_filenames() -> None:
    assert classify_path("downloads/anime/foo/Season 1/garbage.mp4") is None


# --- rescan driver -----------------------------------------------------


def _write_success_log(lines: list[str]) -> Path:
    paths.logs_dir().mkdir(parents=True, exist_ok=True)
    path = paths.logs_dir() / "success.log"
    path.write_text("\n".join(lines) + "\n")
    return path


def test_rescan_populates_library_from_log() -> None:
    _write_success_log([
        "[2026-04-23T10:00:00+00:00] downloads/anime/oshi-no-ko/Season 1/oshi-no-ko-s1e1-german.mp4 :: size=1000",
        "[2026-04-23T10:00:00+00:00] downloads/anime/oshi-no-ko/Season 1/oshi-no-ko-s1e2-german.mp4 :: size=1000",
        "[2026-04-23T10:00:00+00:00] downloads/serie/breaking-bad/Season 1/breaking-bad-s1e1-german.mp4 :: size=1000",
    ])
    report = rescan_success_log()
    assert len(report.items) == 3
    assert report.skipped == []

    oshi = LibraryStore().get(KIND_LIBRARY, "aniworldto::oshi-no-ko")
    assert oshi["seasons"]["1"]["downloaded"] == [1, 2]

    bb = LibraryStore().get(KIND_LIBRARY, "sto::breaking-bad")
    assert bb["seasons"]["1"]["downloaded"] == [1]


def test_rescan_handles_movies() -> None:
    _write_success_log([
        "[2026-04-23T10:00:00+00:00] downloads/anime/some-anime/movies/some-anime-movie-1-german.mp4 :: size=5000",
    ])
    report = rescan_success_log()
    assert len(report.items) == 1

    entry = LibraryStore().get(KIND_LIBRARY, "aniworldto::some-anime")
    assert entry["movies"]["downloaded"] == [1]


def test_rescan_collects_skipped_unknown_paths() -> None:
    _write_success_log([
        "[ts] downloads/random/thing.mp4 :: size=1",
        "[ts] downloads/anime/foo/Season 1/foo-s1e1-de.mp4 :: size=1",
    ])
    report = rescan_success_log()
    assert len(report.items) == 1
    assert len(report.skipped) == 1
    assert "random" in report.skipped[0]


def test_rescan_ignores_blank_lines() -> None:
    _write_success_log([
        "",
        "   ",
        "[ts] downloads/anime/foo/Season 1/foo-s1e1-de.mp4 :: size=1",
    ])
    report = rescan_success_log()
    assert len(report.items) == 1


def test_rescan_survives_malformed_log_line() -> None:
    _write_success_log([
        "not a valid log line",
        "[ts] downloads/anime/foo/Season 1/foo-s1e1-de.mp4 :: size=1",
    ])
    report = rescan_success_log()
    # First line parses as '<no-timestamp> not a valid log line' → no path → skipped silently.
    assert len(report.items) == 1


def test_rescan_missing_log_returns_empty_report() -> None:
    report = rescan_success_log()
    assert report.items == []
    assert report.skipped == []


def test_rescan_is_idempotent() -> None:
    """Running rescan twice must not duplicate episodes in downloaded arrays."""
    _write_success_log([
        "[ts] downloads/anime/foo/Season 1/foo-s1e1-de.mp4 :: size=1",
        "[ts] downloads/anime/foo/Season 1/foo-s1e2-de.mp4 :: size=1",
    ])
    rescan_success_log()
    rescan_success_log()
    entry = LibraryStore().get(KIND_LIBRARY, "aniworldto::foo")
    assert entry["seasons"]["1"]["downloaded"] == [1, 2]  # no dupes
