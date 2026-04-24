"""Paket H+1 — `streamseeker daemon restart` command."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from cleo.application import Application
from cleo.testers.command_tester import CommandTester

from streamseeker.console.commands.daemon.restart import DaemonRestartCommand
from streamseeker.daemon.lifecycle import DaemonStatus


def _run(argv: str = "") -> tuple[int, str]:
    app = Application()
    app.add(DaemonRestartCommand())
    tester = CommandTester(app.find("daemon restart"))
    return tester.execute(argv), tester.io.fetch_output()


@pytest.fixture
def patched_lifecycle():
    """Expose a single place to tweak lifecycle behavior per test."""
    with patch("streamseeker.console.commands.daemon.restart.lifecycle") as mock:
        yield mock


def test_restart_stops_running_daemon_and_starts_again(patched_lifecycle) -> None:
    patched_lifecycle.is_running.return_value = True
    patched_lifecycle.stop.return_value = True
    patched_lifecycle.start.return_value = DaemonStatus(running=True, pid=123)

    exit_code, output = _run()
    assert exit_code == 0
    patched_lifecycle.stop.assert_called_once()
    patched_lifecycle.start.assert_called_once_with(foreground=False)
    assert "Daemon stopped" in output
    assert "Daemon restarted" in output
    assert "pid 123" in output


def test_restart_starts_when_daemon_not_running(patched_lifecycle) -> None:
    patched_lifecycle.is_running.return_value = False
    patched_lifecycle.start.return_value = DaemonStatus(running=True, pid=456)

    exit_code, output = _run()
    assert exit_code == 0
    patched_lifecycle.stop.assert_not_called()
    assert "starting fresh" in output.lower()


def test_restart_exits_1_when_stop_fails(patched_lifecycle) -> None:
    patched_lifecycle.is_running.return_value = True
    patched_lifecycle.stop.return_value = False

    exit_code, output = _run()
    assert exit_code == 1
    assert "Could not stop" in output


def test_restart_propagates_port_in_use_error(patched_lifecycle) -> None:
    patched_lifecycle.is_running.return_value = False
    patched_lifecycle.start.side_effect = OSError("port 8765 is already in use")

    exit_code, output = _run()
    assert exit_code == 2
    assert "already in use" in output


def test_restart_foreground_flag_propagates(patched_lifecycle) -> None:
    patched_lifecycle.is_running.return_value = False
    patched_lifecycle.start.return_value = DaemonStatus(running=False)

    exit_code, _ = _run("--foreground")
    assert exit_code == 0
    patched_lifecycle.start.assert_called_once_with(foreground=True)
