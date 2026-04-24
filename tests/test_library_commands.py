"""Paket C — CLI commands for favorites and library."""

from __future__ import annotations

from pathlib import Path

import pytest
from cleo.application import Application
from cleo.testers.command_tester import CommandTester

from streamseeker.api.core.helpers import Singleton
from streamseeker.api.core.library import LibraryStore
from streamseeker.api.core.library.store import KIND_FAVORITES, KIND_LIBRARY
from streamseeker.console.commands.favorite.add import FavoriteAddCommand
from streamseeker.console.commands.favorite.list import FavoriteListCommand
from streamseeker.console.commands.favorite.promote import FavoritePromoteCommand
from streamseeker.console.commands.favorite.remove import FavoriteRemoveCommand
from streamseeker.console.commands.favorite.search import FavoriteSearchCommand
from streamseeker.console.commands.library.list import LibraryListCommand
from streamseeker.console.commands.library.remove import LibraryRemoveCommand
from streamseeker.console.commands.library.search import LibrarySearchCommand
from streamseeker.console.commands.library.show import LibraryShowCommand
from streamseeker.console.commands.library.stats import LibraryStatsCommand


@pytest.fixture(autouse=True)
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STREAMSEEKER_HOME", str(tmp_path))
    Singleton._instances.pop(LibraryStore, None)
    yield
    Singleton._instances.pop(LibraryStore, None)


def _run(cmd_cls, argv: str = "") -> tuple[int, str]:
    app = Application()
    app.add(cmd_cls())
    tester = CommandTester(app.find(cmd_cls.name))
    exit_code = tester.execute(argv)
    return exit_code, tester.io.fetch_output()


# --- favorite add -----------------------------------------------------


def test_favorite_add_creates_entry() -> None:
    exit_code, output = _run(FavoriteAddCommand, "aniworldto oshi-no-ko")
    assert exit_code == 0
    assert "Oshi No Ko" in output
    assert LibraryStore().get(KIND_FAVORITES, "aniworldto::oshi-no-ko") is not None


def test_favorite_add_is_idempotent() -> None:
    _run(FavoriteAddCommand, "aniworldto oshi-no-ko")
    exit_code, _ = _run(FavoriteAddCommand, "aniworldto oshi-no-ko")
    assert exit_code == 0
    assert len(LibraryStore().list(KIND_FAVORITES)) == 1


# --- favorite remove --------------------------------------------------


def test_favorite_remove_existing() -> None:
    _run(FavoriteAddCommand, "sto breaking-bad")
    exit_code, output = _run(FavoriteRemoveCommand, "sto breaking-bad")
    assert exit_code == 0
    assert "Removed favorite" in output
    assert LibraryStore().list(KIND_FAVORITES) == []


def test_favorite_remove_missing_returns_nonzero() -> None:
    exit_code, output = _run(FavoriteRemoveCommand, "sto ghost")
    assert exit_code == 1
    assert "No favorite" in output


# --- favorite list ----------------------------------------------------


def test_favorite_list_shows_all() -> None:
    _run(FavoriteAddCommand, "sto breaking-bad")
    _run(FavoriteAddCommand, "aniworldto oshi-no-ko")
    exit_code, output = _run(FavoriteListCommand)
    assert exit_code == 0
    assert "Breaking Bad" in output
    assert "Oshi No Ko" in output


def test_favorite_list_empty_message() -> None:
    exit_code, output = _run(FavoriteListCommand)
    assert exit_code == 0
    assert "No favorites" in output


# --- favorite search --------------------------------------------------


def test_favorite_search_matches_by_title() -> None:
    _run(FavoriteAddCommand, "aniworldto oshi-no-ko")
    _run(FavoriteAddCommand, "sto breaking-bad")
    exit_code, output = _run(FavoriteSearchCommand, "breaking")
    assert exit_code == 0
    assert "Breaking Bad" in output
    assert "Oshi No Ko" not in output


def test_favorite_search_no_match() -> None:
    exit_code, output = _run(FavoriteSearchCommand, "nope")
    assert exit_code == 0
    assert "No favorites match" in output


# --- favorite promote -------------------------------------------------


def test_favorite_promote_moves_into_library() -> None:
    _run(FavoriteAddCommand, "aniworldto chainsaw-man")
    exit_code, output = _run(FavoritePromoteCommand, "aniworldto chainsaw-man")
    assert exit_code == 0
    assert "Promoted to Library" in output

    assert LibraryStore().get(KIND_FAVORITES, "aniworldto::chainsaw-man") is None
    assert LibraryStore().get(KIND_LIBRARY, "aniworldto::chainsaw-man") is not None


def test_favorite_promote_unknown_errors() -> None:
    exit_code, output = _run(FavoritePromoteCommand, "sto ghost")
    assert exit_code == 1
    assert "No favorite" in output


# --- library list / search / show -----------------------------------


def test_library_list_empty() -> None:
    exit_code, output = _run(LibraryListCommand)
    assert exit_code == 0
    assert "Library is empty" in output


def test_library_list_shows_entries() -> None:
    LibraryStore().mark_episode_downloaded("sto::breaking-bad", 1, 1)
    exit_code, output = _run(LibraryListCommand)
    assert exit_code == 0
    assert "Breaking Bad" in output


def test_library_search_finds_entry() -> None:
    LibraryStore().mark_episode_downloaded("sto::breaking-bad", 1, 1)
    exit_code, output = _run(LibrarySearchCommand, "breaking")
    assert exit_code == 0
    assert "Breaking Bad" in output


def test_library_show_prints_details() -> None:
    LibraryStore().mark_episode_downloaded("sto::breaking-bad", 1, 1)
    exit_code, output = _run(LibraryShowCommand, "sto breaking-bad")
    assert exit_code == 0
    assert "Breaking Bad" in output
    assert "Season 1" in output


def test_library_show_missing_errors() -> None:
    exit_code, output = _run(LibraryShowCommand, "sto ghost")
    assert exit_code == 1
    assert "Not in Library" in output


# --- library stats ----------------------------------------------------


def test_library_stats_summarizes_counts() -> None:
    LibraryStore().mark_episode_downloaded("sto::breaking-bad", 1, 1)
    LibraryStore().mark_episode_downloaded("sto::breaking-bad", 1, 2)
    LibraryStore().mark_episode_downloaded("aniworldto::oshi-no-ko", 1, 1)

    exit_code, output = _run(LibraryStatsCommand)
    assert exit_code == 0
    assert "2 entries" in output
    assert "3 episodes" in output
    assert "sto" in output and "aniworldto" in output
    assert "Most complete" in output


def test_library_stats_empty() -> None:
    exit_code, output = _run(LibraryStatsCommand)
    assert exit_code == 0
    assert "Library is empty" in output


# --- library remove ---------------------------------------------------


def test_library_remove_existing() -> None:
    LibraryStore().mark_episode_downloaded("sto::breaking-bad", 1, 1)
    exit_code, output = _run(LibraryRemoveCommand, "sto breaking-bad")
    assert exit_code == 0
    assert "Removed from Library" in output
    assert LibraryStore().list(KIND_LIBRARY) == []


def test_library_remove_missing() -> None:
    exit_code, output = _run(LibraryRemoveCommand, "sto ghost")
    assert exit_code == 1
    assert "Not in Library" in output
