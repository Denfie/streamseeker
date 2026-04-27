"""Paket G.6 — library refresh CLI + daemon endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from cleo.application import Application
from cleo.testers.command_tester import CommandTester
from fastapi.testclient import TestClient

from streamseeker import paths
from streamseeker.api.core.helpers import Singleton
from streamseeker.api.core.library import LibraryStore
from streamseeker.api.core.library.store import KIND_LIBRARY
from streamseeker.api.core.metadata.resolver import MetadataResolver
from streamseeker.console.commands.library.refresh import LibraryRefreshCommand
from streamseeker.daemon.server import create_app


@pytest.fixture(autouse=True)
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STREAMSEEKER_HOME", str(tmp_path))
    Singleton._instances.pop(LibraryStore, None)
    yield
    Singleton._instances.pop(LibraryStore, None)


def _run_cli(argv: str) -> tuple[int, str]:
    app = Application()
    app.add(LibraryRefreshCommand())
    tester = CommandTester(app.find("library refresh"))
    return tester.execute(argv), tester.io.fetch_output()


# --- CLI command ----------------------------------------------------


def test_cli_refresh_single_succeeds_when_resolver_applies() -> None:
    LibraryStore().mark_episode_downloaded("aniworldto::oshi-no-ko", 1, 1)
    with patch.object(MetadataResolver, "enrich", return_value=True):
        exit_code, output = _run_cli("aniworldto oshi-no-ko")
    assert exit_code == 0
    assert "Refreshed" in output


def test_cli_refresh_single_prints_no_change_when_resolver_returns_false() -> None:
    with patch.object(MetadataResolver, "enrich", return_value=False):
        exit_code, output = _run_cli("sto ghost")
    assert exit_code == 1
    assert "No changes" in output


def test_cli_refresh_needs_args_without_all() -> None:
    exit_code, output = _run_cli("")
    assert exit_code == 2
    assert "--all" in output


def test_cli_refresh_all_iterates_every_entry() -> None:
    LibraryStore().mark_episode_downloaded("aniworldto::oshi-no-ko", 1, 1)
    LibraryStore().mark_episode_downloaded("sto::breaking-bad", 1, 1)
    with patch.object(MetadataResolver, "enrich", return_value=True) as mock_enrich:
        exit_code, output = _run_cli("--all")
    assert exit_code == 0
    assert mock_enrich.call_count == 2
    assert "Refreshed 2/2" in output


def test_cli_refresh_all_on_empty_library() -> None:
    exit_code, output = _run_cli("--all")
    assert exit_code == 0
    assert "Library is empty" in output


# --- Daemon endpoints ----------------------------------------------


def test_daemon_refresh_endpoint_calls_resolver() -> None:
    LibraryStore().mark_episode_downloaded("sto::breaking-bad", 1, 1)
    client = TestClient(create_app())
    with patch.object(MetadataResolver, "enrich", return_value=True):
        response = client.post("/library/sto::breaking-bad/refresh")
    assert response.status_code == 200
    body = response.json()
    assert body["refreshed"] is True
    assert body["key"] == "sto::breaking-bad"


def test_daemon_refresh_404_for_unknown_entry() -> None:
    client = TestClient(create_app())
    response = client.post("/library/sto::ghost/refresh")
    assert response.status_code == 404


def test_daemon_refresh_all_kicks_off_paced_worker() -> None:
    LibraryStore().mark_episode_downloaded("sto::breaking-bad", 1, 1)
    LibraryStore().mark_episode_downloaded("sto::other-show", 1, 1)
    client = TestClient(create_app())
    with patch.object(MetadataResolver, "enrich", return_value=True) as enrich:
        # delay=0 so the worker doesn't actually sleep during the test
        response = client.post("/library/refresh-all?reset=true&delay=0")
        assert response.status_code == 200
        body = response.json()
        assert body["queued"] == 2
        assert body["delay_seconds"] == 0.0
        # Wait briefly for the daemon thread to consume the keys.
        import time
        for _ in range(50):
            if enrich.call_count >= 2:
                break
            time.sleep(0.01)
        assert enrich.call_count == 2
        # `reset=true` must propagate through to the resolver.
        for call in enrich.call_args_list:
            assert call.kwargs.get("reset") is True


def test_daemon_poster_endpoint_serves_file() -> None:
    LibraryStore().mark_episode_downloaded("sto::breaking-bad", 1, 1)
    asset = paths.series_dir(KIND_LIBRARY, "sto", "breaking-bad")
    asset.mkdir(parents=True, exist_ok=True)
    (asset / "poster.jpg").write_bytes(b"\xff\xd8\xff\xe0FAKEJPEG")

    client = TestClient(create_app())
    response = client.get("/library/sto::breaking-bad/poster")
    assert response.status_code == 200
    assert response.content.startswith(b"\xff\xd8\xff")


def test_daemon_poster_404_for_missing_asset() -> None:
    client = TestClient(create_app())
    response = client.get("/library/sto::ghost/poster")
    assert response.status_code == 404


def test_daemon_backdrop_404_when_no_file() -> None:
    LibraryStore().mark_episode_downloaded("sto::breaking-bad", 1, 1)
    client = TestClient(create_app())
    response = client.get("/library/sto::breaking-bad/backdrop")
    assert response.status_code == 404


def test_daemon_poster_rejects_invalid_key_shape() -> None:
    client = TestClient(create_app())
    response = client.get("/library/not-a-key/poster")
    assert response.status_code == 404
