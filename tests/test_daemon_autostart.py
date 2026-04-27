"""Paket D.5 — unit-test the autostart adapters' rendering and dispatch.

Actual ``launchctl``/``systemctl`` invocations are not exercised here —
they require root-level OS state that pytest shouldn't touch. Those
code paths are covered by the manual install/uninstall CLI test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from streamseeker.daemon import autostart
from streamseeker.daemon.autostart import (
    LABEL,
    AutostartUnavailableError,
    LaunchdAdapter,
    SystemdUserAdapter,
    get_adapter,
)


@pytest.fixture(autouse=True)
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STREAMSEEKER_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))  # adapters use Path.home()
    yield


# --- LaunchD ----------------------------------------------------------


def test_launchd_unit_path_under_library() -> None:
    path = LaunchdAdapter().unit_path()
    assert path.parts[-3:] == ("Library", "LaunchAgents", f"{LABEL}.plist")


def test_launchd_render_includes_core_elements() -> None:
    plist = LaunchdAdapter().render()
    assert '<?xml version="1.0"' in plist
    assert f"<string>{LABEL}</string>" in plist
    assert "<string>streamseeker</string>" in plist
    assert "<string>daemon</string>" in plist
    assert "<string>--foreground</string>" in plist
    assert "<key>KeepAlive</key>" in plist
    assert "<key>RunAtLoad</key>" in plist


def test_launchd_render_includes_env_override_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STREAMSEEKER_HOME", "/custom/home")
    plist = LaunchdAdapter().render()
    assert "EnvironmentVariables" in plist
    assert "/custom/home" in plist


def test_launchd_render_omits_env_block_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STREAMSEEKER_HOME", raising=False)
    plist = LaunchdAdapter().render()
    assert "EnvironmentVariables" not in plist


def test_launchd_uninstall_returns_false_when_missing() -> None:
    assert LaunchdAdapter().uninstall() is False


# --- systemd ----------------------------------------------------------


def test_systemd_unit_path_under_config_systemd_user() -> None:
    path = SystemdUserAdapter().unit_path()
    assert path.parts[-3:] == ("systemd", "user", "streamseeker.service")


def test_systemd_render_has_required_sections() -> None:
    unit = SystemdUserAdapter().render()
    assert "[Unit]" in unit
    assert "[Service]" in unit
    assert "[Install]" in unit
    assert "Type=simple" in unit
    assert "--foreground" in unit
    assert "Restart=always" in unit
    assert "StartLimitBurst=" in unit
    assert "WantedBy=default.target" in unit


def test_systemd_render_includes_env_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STREAMSEEKER_HOME", "/tmp/ss")
    unit = SystemdUserAdapter().render()
    assert "Environment=STREAMSEEKER_HOME=/tmp/ss" in unit


def test_systemd_uninstall_returns_false_when_missing() -> None:
    assert SystemdUserAdapter().uninstall() is False


# --- dispatcher -------------------------------------------------------


def test_get_adapter_returns_launchd_on_darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert isinstance(get_adapter(), LaunchdAdapter)


def test_get_adapter_returns_systemd_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(autostart.shutil, "which", lambda _: "/usr/bin/systemctl")
    assert isinstance(get_adapter(), SystemdUserAdapter)


def test_get_adapter_raises_on_linux_without_systemd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(autostart.shutil, "which", lambda _: None)
    with pytest.raises(AutostartUnavailableError):
        get_adapter()


def test_get_adapter_raises_on_unsupported_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    # Windows is now supported (Paket H) — pick a truly exotic platform.
    monkeypatch.setattr(sys, "platform", "openbsd7")
    with pytest.raises(AutostartUnavailableError):
        get_adapter()


# --- install writes the file without activation ---------------------


def test_install_writes_file_and_calls_activate(monkeypatch: pytest.MonkeyPatch) -> None:
    """`install()` must write the unit AND call `activate()`.

    We stub `activate` so no real launchctl/systemctl call happens.
    """
    called = []
    adapter = SystemdUserAdapter()
    monkeypatch.setattr(adapter, "activate", lambda: called.append("activate"))

    written = adapter.install()
    assert written.is_file()
    assert called == ["activate"]
    assert "streamseeker" in written.read_text()
