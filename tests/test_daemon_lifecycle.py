"""Lifecycle unit tests for the daemon (no live uvicorn).

The real fork + uvicorn path is integration-tested manually (see CHANGELOG).
Here we verify the PID-file bookkeeping and non-forking helpers in isolation.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from streamseeker import paths
from streamseeker.daemon import lifecycle


@pytest.fixture(autouse=True)
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STREAMSEEKER_HOME", str(tmp_path))
    yield


def test_status_reports_not_running_when_pid_file_missing() -> None:
    assert lifecycle.status().running is False
    assert lifecycle.is_running() is False


def test_status_is_running_when_pid_alive() -> None:
    # Use our own PID — it's guaranteed alive for the duration of the test.
    paths.daemon_pid_file().parent.mkdir(parents=True, exist_ok=True)
    paths.daemon_pid_file().write_text(str(os.getpid()))
    status = lifecycle.status()
    assert status.running is True
    assert status.pid == os.getpid()


def test_status_clears_stale_pid_file() -> None:
    # Write a PID that certainly does not exist.
    paths.daemon_pid_file().parent.mkdir(parents=True, exist_ok=True)
    paths.daemon_pid_file().write_text("999999")
    status = lifecycle.status()
    assert status.running is False
    assert not paths.daemon_pid_file().exists()


def test_status_tolerates_garbage_pid_file() -> None:
    paths.daemon_pid_file().parent.mkdir(parents=True, exist_ok=True)
    paths.daemon_pid_file().write_text("nope")
    status = lifecycle.status()
    assert status.running is False


def test_describe_returns_expected_keys() -> None:
    info = lifecycle.describe()
    assert {"running", "host", "port", "pid_file"} <= info.keys()
    assert info["host"] == lifecycle.DAEMON_HOST
    assert info["port"] == lifecycle.DAEMON_PORT


def test_stop_returns_false_when_not_running() -> None:
    assert lifecycle.stop() is False


def test_start_raises_when_already_running(monkeypatch: pytest.MonkeyPatch) -> None:
    # Fake a running daemon via PID file pointing to this process.
    paths.daemon_pid_file().parent.mkdir(parents=True, exist_ok=True)
    paths.daemon_pid_file().write_text(str(os.getpid()))

    with pytest.raises(lifecycle.DaemonAlreadyRunningError) as exc_info:
        lifecycle.start()
    assert exc_info.value.pid == os.getpid()


def test_ensure_port_free_raises_on_conflict() -> None:
    """Bind the configured port manually, then verify start detects it.

    Skipped if the real daemon happens to be listening on 8765 already —
    that's the same condition the test is checking, so the behavior is
    already proven by the environment.
    """
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((lifecycle.DAEMON_HOST, lifecycle.DAEMON_PORT))
        except OSError:
            pytest.skip(f"port {lifecycle.DAEMON_PORT} already in use — "
                        "stop the local daemon to run this test")
        s.listen(1)

        with pytest.raises(OSError):
            lifecycle._ensure_port_free()
    finally:
        s.close()
