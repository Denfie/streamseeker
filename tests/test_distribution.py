"""Paket H — install-extension, install-desktop-icon, uninstall, sources."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from cleo.application import Application
from cleo.testers.command_tester import CommandTester

from streamseeker import paths
from streamseeker.console.commands.install_desktop_icon import (
    InstallDesktopIconCommand,
)
from streamseeker.console.commands.install_extension import InstallExtensionCommand
from streamseeker.console.commands.uninstall import UninstallCommand
from streamseeker.console.commands.uninstall_desktop_icon import (
    UninstallDesktopIconCommand,
)
from streamseeker.console.commands.uninstall_extension import UninstallExtensionCommand
from streamseeker.distribution import desktop as desktop_icon
from streamseeker.distribution.sources import source_extension_dir


@pytest.fixture(autouse=True)
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STREAMSEEKER_HOME", str(tmp_path))
    # Prevent every test from poking real ~/Desktop or browser.
    monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
    (tmp_path / "fakehome").mkdir()
    yield


def _run(cmd_cls, argv: str = "") -> tuple[int, str]:
    app = Application()
    app.add(cmd_cls())
    tester = CommandTester(app.find(cmd_cls.name))
    return tester.execute(argv), tester.io.fetch_output()


# --- source discovery ----------------------------------------------


def test_source_extension_dir_finds_repo_checkout() -> None:
    src = source_extension_dir()
    assert src.is_dir()
    assert (src / "manifest.json").is_file()


# --- install-extension ---------------------------------------------


def test_install_extension_copies_and_prints_steps() -> None:
    with patch(
        "streamseeker.console.commands.install_extension._open_extensions_page"
    ) as mock_open:
        exit_code, output = _run(InstallExtensionCommand, "--no-open")
    assert exit_code == 0
    target = paths.extension_dir()
    assert (target / "manifest.json").is_file()
    assert "Next steps" in output
    mock_open.assert_not_called()


def test_install_extension_refuses_to_overwrite_without_update() -> None:
    paths.extension_dir().mkdir(parents=True)
    (paths.extension_dir() / "manifest.json").write_text("{}")
    exit_code, output = _run(InstallExtensionCommand, "--no-open")
    assert exit_code == 1
    assert "--update" in output


def test_install_extension_update_overwrites() -> None:
    paths.extension_dir().mkdir(parents=True)
    (paths.extension_dir() / "stale.txt").write_text("old")
    exit_code, _ = _run(InstallExtensionCommand, "--no-open --update")
    assert exit_code == 0
    assert not (paths.extension_dir() / "stale.txt").exists()
    assert (paths.extension_dir() / "manifest.json").is_file()


def test_install_extension_opens_browser_by_default() -> None:
    with patch(
        "streamseeker.console.commands.install_extension._open_extensions_page"
    ) as mock_open:
        exit_code, _ = _run(InstallExtensionCommand, "")
    assert exit_code == 0
    mock_open.assert_called_once()


# --- uninstall-extension -------------------------------------------


def test_uninstall_extension_removes_folder() -> None:
    paths.extension_dir().mkdir(parents=True)
    (paths.extension_dir() / "x.txt").write_text(".")
    exit_code, output = _run(UninstallExtensionCommand)
    assert exit_code == 0
    assert not paths.extension_dir().exists()
    assert "Removed" in output


def test_uninstall_extension_noop_if_missing() -> None:
    exit_code, output = _run(UninstallExtensionCommand)
    assert exit_code == 1
    assert "No extension" in output


# --- desktop icon --------------------------------------------------


def test_install_desktop_icon_macos_creates_command_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    exit_code, _ = _run(InstallDesktopIconCommand)
    assert exit_code == 0
    command_file = Path.home() / "Desktop" / "StreamSeeker.command"
    assert command_file.is_file()
    assert "open" in command_file.read_text()
    # must be executable
    assert command_file.stat().st_mode & 0o111


def test_install_desktop_icon_linux_writes_desktop_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    (Path.home() / "Desktop").mkdir()
    exit_code, _ = _run(InstallDesktopIconCommand)
    assert exit_code == 0
    apps_file = Path.home() / ".local" / "share" / "applications" / "streamseeker.desktop"
    assert apps_file.is_file()
    content = apps_file.read_text()
    assert "[Desktop Entry]" in content
    assert "xdg-open" in content


def test_uninstall_desktop_icon_removes_all_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    _run(InstallDesktopIconCommand)
    exit_code, output = _run(UninstallDesktopIconCommand)
    assert exit_code == 0
    assert "Removed" in output
    assert not (Path.home() / "Desktop" / "StreamSeeker.command").exists()


def test_uninstall_desktop_icon_noop_when_missing() -> None:
    exit_code, output = _run(UninstallDesktopIconCommand)
    assert exit_code == 1
    assert "No desktop icon" in output


# --- uninstall (aggregate) -----------------------------------------


def test_uninstall_runs_all_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pre-create all artifacts so the aggregate uninstall has something to do.
    paths.extension_dir().mkdir(parents=True)
    (paths.extension_dir() / "manifest.json").write_text("{}")

    # Stub out autostart + desktop + daemon-stop to avoid OS side effects.
    from streamseeker.console.commands import uninstall as uninstall_mod

    class FakeAdapter:
        def uninstall(self): return True

    monkeypatch.setattr(uninstall_mod, "get_adapter", lambda: FakeAdapter())
    monkeypatch.setattr(uninstall_mod.desktop_icon, "uninstall", lambda: [Path("/fake/icon")])
    monkeypatch.setattr(uninstall_mod.lifecycle, "is_running", lambda: False)

    exit_code, output = _run(UninstallCommand, "--force")
    assert exit_code == 0
    assert not paths.extension_dir().exists()
    assert "Uninstall complete" in output


def test_uninstall_purge_deletes_home(monkeypatch: pytest.MonkeyPatch) -> None:
    # Put something under ~/.streamseeker/
    paths.logs_dir().mkdir(parents=True)
    (paths.logs_dir() / "marker").write_text("x")

    from streamseeker.console.commands import uninstall as uninstall_mod

    class FakeAdapter:
        def uninstall(self): return False

    monkeypatch.setattr(uninstall_mod, "get_adapter", lambda: FakeAdapter())
    monkeypatch.setattr(uninstall_mod.desktop_icon, "uninstall", lambda: [])
    monkeypatch.setattr(uninstall_mod.lifecycle, "is_running", lambda: False)

    exit_code, output = _run(UninstallCommand, "--force --purge")
    assert exit_code == 0
    assert not paths.home().exists()
    assert "removed" in output.lower()


def test_uninstall_without_force_exits_on_decline(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the user answers "no", nothing is removed."""
    from streamseeker.console.commands import uninstall as uninstall_mod
    monkeypatch.setattr(uninstall_mod.lifecycle, "is_running", lambda: False)

    # Pre-create extension folder; declining the prompt must keep it.
    paths.extension_dir().mkdir(parents=True)
    (paths.extension_dir() / "m.json").write_text("{}")

    app = Application()
    app.add(UninstallCommand())
    tester = CommandTester(app.find("uninstall"))
    tester.execute("", inputs="no\n")

    assert paths.extension_dir().exists()  # unchanged


# --- Windows autostart adapter (construction only) -----------------


def test_windows_task_scheduler_render_contains_foreground_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from streamseeker.daemon import autostart

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(autostart.shutil, "which", lambda _: "schtasks.exe")
    adapter = autostart.get_adapter()
    assert isinstance(adapter, autostart.WindowsTaskSchedulerAdapter)
    command = adapter.render()
    assert "streamseeker" in command
    assert "--foreground" in command
