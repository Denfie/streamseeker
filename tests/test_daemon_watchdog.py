"""Tests for the in-process daemon watchdog and the /health endpoint."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from streamseeker.api.core.downloader.manager import DownloadManager
from streamseeker.api.core.helpers import Singleton
from streamseeker.api.core.library import LibraryStore
from streamseeker.daemon.server import create_app
from streamseeker.daemon.watchdog import Watchdog


@pytest.fixture(autouse=True)
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STREAMSEEKER_HOME", str(tmp_path))
    Singleton._instances.pop(DownloadManager, None)
    Singleton._instances.pop(LibraryStore, None)
    from streamseeker.daemon import server as _server
    _server._invalidate_library_state_cache()
    yield
    Singleton._instances.pop(DownloadManager, None)
    Singleton._instances.pop(LibraryStore, None)
    _server._invalidate_library_state_cache()


# --- /health endpoint --------------------------------------------------


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "ts" in payload


# --- Watchdog probe behavior -------------------------------------------


def test_watchdog_probe_succeeds_when_health_responds() -> None:
    wd = Watchdog(host="127.0.0.1", port=8765)
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value.status = 200
        ok, reason = wd._probe()
    assert ok is True
    assert reason == "ok"


def test_watchdog_probe_fails_on_connection_error() -> None:
    wd = Watchdog(host="127.0.0.1", port=8765)
    import urllib.error

    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("connection refused"),
    ):
        ok, reason = wd._probe()
    assert ok is False
    assert "URLError" in reason


def test_watchdog_probe_fails_on_non_2xx_status() -> None:
    wd = Watchdog(host="127.0.0.1", port=8765)
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value.status = 503
        ok, reason = wd._probe()
    assert ok is False
    assert "503" in reason


# --- force-exit triggers on consecutive failures -----------------------


def test_watchdog_force_exits_after_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    wd = Watchdog(
        host="127.0.0.1",
        port=8765,
        interval=0.05,
        timeout=0.05,
        failure_threshold=2,
        startup_grace=0.0,
    )
    exits: list[int] = []
    monkeypatch.setattr("os._exit", lambda code: exits.append(code))
    monkeypatch.setattr(wd, "_probe", lambda: (False, "boom"))

    wd.start()
    # Wait long enough for two intervals + a margin.
    assert wd._thread is not None
    wd._thread.join(timeout=2.0)
    wd.stop()

    assert exits == [1], "watchdog should call os._exit(1) once threshold is hit"


def test_watchdog_resets_failure_counter_on_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wd = Watchdog(
        host="127.0.0.1",
        port=8765,
        interval=0.02,
        timeout=0.05,
        failure_threshold=3,
        startup_grace=0.0,
    )
    exits: list[int] = []
    monkeypatch.setattr("os._exit", lambda code: exits.append(code))

    # Probe sequence: fail, fail, succeed, fail, fail — never three in a row.
    sequence = iter(
        [
            (False, "x"),
            (False, "x"),
            (True, "ok"),
            (False, "x"),
            (False, "x"),
        ]
    )
    monkeypatch.setattr(wd, "_probe", lambda: next(sequence, (True, "ok")))

    wd.start()
    # Let the loop iterate through the sequence.
    import time

    time.sleep(0.3)
    wd.stop()

    assert exits == [], "watchdog must not exit when failures don't run consecutively"


def test_watchdog_can_be_stopped_cleanly() -> None:
    wd = Watchdog(host="127.0.0.1", port=8765, interval=10.0, startup_grace=0.0)
    wd.start()
    assert wd._thread is not None
    wd.stop()
    # After stop the thread should be gone or finished.
    assert wd._thread is None


# --- processor self-heal -----------------------------------------------


def _seed_queue(tmp_path: Path, items: list[dict]) -> None:
    """Write a minimal queue file under STREAMSEEKER_HOME so DownloadManager
    sees the items we want."""
    import json

    from streamseeker import paths

    queue_file = paths.queue_file()
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    queue_file.write_text(json.dumps(items))


def test_watchdog_heal_restarts_processor_when_pending_items_exist(
    tmp_path: Path,
) -> None:
    from streamseeker.api.core.downloader.processor import QueueProcessor

    _seed_queue(
        tmp_path,
        [{"file_name": "a.mp4", "status": "pending"}],
    )
    Singleton._instances.pop(QueueProcessor, None)

    wd = Watchdog(host="127.0.0.1", port=8765, startup_grace=0.0)
    with patch.object(QueueProcessor, "is_running", return_value=False), \
         patch.object(QueueProcessor, "start") as mock_start:
        wd._heal_processor_if_needed()
        mock_start.assert_called_once()

    Singleton._instances.pop(QueueProcessor, None)


def test_watchdog_heal_restarts_processor_for_zombie_downloads(
    tmp_path: Path,
) -> None:
    """The exact failure mode we saw in the wild: items stuck at 'downloading'
    because the previous run died mid-flight. Only ``processor.start()`` resets
    them via _recover_interrupted, so the watchdog must trigger that path."""
    from streamseeker.api.core.downloader.processor import QueueProcessor

    _seed_queue(
        tmp_path,
        [{"file_name": "zombie.mp4", "status": "downloading"}],
    )
    Singleton._instances.pop(QueueProcessor, None)

    wd = Watchdog(host="127.0.0.1", port=8765, startup_grace=0.0)
    with patch.object(QueueProcessor, "is_running", return_value=False), \
         patch.object(QueueProcessor, "start") as mock_start:
        wd._heal_processor_if_needed()
        mock_start.assert_called_once()

    Singleton._instances.pop(QueueProcessor, None)


def test_watchdog_heal_skips_when_queue_empty(tmp_path: Path) -> None:
    from streamseeker.api.core.downloader.processor import QueueProcessor

    _seed_queue(tmp_path, [{"file_name": "done.mp4", "status": "success"}])
    Singleton._instances.pop(QueueProcessor, None)

    wd = Watchdog(host="127.0.0.1", port=8765, startup_grace=0.0)
    with patch.object(QueueProcessor, "is_running", return_value=False), \
         patch.object(QueueProcessor, "start") as mock_start:
        wd._heal_processor_if_needed()
        mock_start.assert_not_called()

    Singleton._instances.pop(QueueProcessor, None)


def test_watchdog_heal_skips_when_processor_already_running(tmp_path: Path) -> None:
    from streamseeker.api.core.downloader.processor import QueueProcessor

    _seed_queue(
        tmp_path,
        [{"file_name": "a.mp4", "status": "pending"}],
    )
    Singleton._instances.pop(QueueProcessor, None)

    wd = Watchdog(host="127.0.0.1", port=8765, startup_grace=0.0)
    with patch.object(QueueProcessor, "is_running", return_value=True), \
         patch.object(QueueProcessor, "start") as mock_start:
        wd._heal_processor_if_needed()
        mock_start.assert_not_called()

    Singleton._instances.pop(QueueProcessor, None)


def test_watchdog_heal_disabled_when_flag_off() -> None:
    wd = Watchdog(
        host="127.0.0.1", port=8765, startup_grace=0.0, heal_processor=False
    )
    assert wd._heal_processor is False
