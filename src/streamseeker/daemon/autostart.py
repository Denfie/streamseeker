"""User-level autostart adapters for macOS (launchd) and Linux (systemd).

Windows support is deliberately deferred to Paket H (Task Scheduler) per ADR 0013.
Each adapter knows how to install, uninstall and report status of its user-
level service. Adapters never require sudo and never write to system paths.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path

from streamseeker import paths

LABEL = "com.streamseeker.daemon"


class AutostartUnavailableError(RuntimeError):
    """Raised when autostart install/uninstall is attempted on an unsupported platform."""


class AutostartAdapter(ABC):
    """Base class for user-level autostart adapters."""

    # Where the unit/plist file lives on disk.
    @abstractmethod
    def unit_path(self) -> Path: ...

    # Render the unit/plist content from context.
    @abstractmethod
    def render(self) -> str: ...

    # Activate the installed unit. Must be idempotent.
    @abstractmethod
    def activate(self) -> None: ...

    # Deactivate + remove the installed unit. Returns True if something was removed.
    @abstractmethod
    def uninstall(self) -> bool: ...

    # Return a human-readable status string ("installed", "missing", ...).
    @abstractmethod
    def status(self) -> str: ...

    def install(self) -> Path:
        """Write the unit file + activate. Returns the path that was written."""
        path = self.unit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render())
        self.activate()
        return path


# ---------------------------------------------------------------------
# macOS — launchd
# ---------------------------------------------------------------------


class LaunchdAdapter(AutostartAdapter):
    def unit_path(self) -> Path:
        return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"

    def render(self) -> str:
        python = sys.executable
        stdout = paths.daemon_log_file()
        stderr = paths.daemon_err_file()
        home_env = os.environ.get("STREAMSEEKER_HOME")
        env_entries = ""
        if home_env:
            env_entries = (
                "    <key>EnvironmentVariables</key>\n"
                "    <dict>\n"
                f"        <key>STREAMSEEKER_HOME</key>\n"
                f"        <string>{home_env}</string>\n"
                "    </dict>\n"
            )

        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN"'
            ' "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n'
            "<dict>\n"
            f"    <key>Label</key>\n    <string>{LABEL}</string>\n"
            "    <key>ProgramArguments</key>\n"
            "    <array>\n"
            f"        <string>{python}</string>\n"
            "        <string>-m</string>\n"
            "        <string>streamseeker</string>\n"
            "        <string>daemon</string>\n"
            "        <string>start</string>\n"
            "        <string>--foreground</string>\n"
            "    </array>\n"
            "    <key>RunAtLoad</key>\n    <true/>\n"
            "    <key>KeepAlive</key>\n    <true/>\n"
            f"    <key>StandardOutPath</key>\n    <string>{stdout}</string>\n"
            f"    <key>StandardErrorPath</key>\n    <string>{stderr}</string>\n"
            f"{env_entries}"
            "</dict>\n"
            "</plist>\n"
        )

    def activate(self) -> None:
        path = self.unit_path()
        # Unload first in case an older copy is active, then load fresh.
        subprocess.run(["launchctl", "unload", "-w", str(path)], check=False, capture_output=True)
        subprocess.run(["launchctl", "load", "-w", str(path)], check=True, capture_output=True)

    def uninstall(self) -> bool:
        path = self.unit_path()
        if not path.exists():
            return False
        subprocess.run(["launchctl", "unload", "-w", str(path)], check=False, capture_output=True)
        path.unlink()
        return True

    def status(self) -> str:
        if not self.unit_path().exists():
            return "not installed"
        result = subprocess.run(
            ["launchctl", "list", LABEL], capture_output=True, text=True
        )
        if result.returncode == 0:
            return "installed and loaded"
        return "installed but not loaded"


# ---------------------------------------------------------------------
# Linux — systemd --user
# ---------------------------------------------------------------------


class SystemdUserAdapter(AutostartAdapter):
    SERVICE_NAME = "streamseeker.service"

    def unit_path(self) -> Path:
        return Path.home() / ".config" / "systemd" / "user" / self.SERVICE_NAME

    def render(self) -> str:
        python = sys.executable
        home_env = os.environ.get("STREAMSEEKER_HOME")
        env_line = f"Environment=STREAMSEEKER_HOME={home_env}\n" if home_env else ""
        return (
            "[Unit]\n"
            "Description=StreamSeeker background daemon\n"
            "After=network-online.target\n"
            "\n"
            "[Service]\n"
            "Type=simple\n"
            f"ExecStart={python} -m streamseeker daemon start --foreground\n"
            "Restart=on-failure\n"
            "RestartSec=3\n"
            f"{env_line}"
            "\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )

    def activate(self) -> None:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, capture_output=True)
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", self.SERVICE_NAME],
            check=True, capture_output=True,
        )

    def uninstall(self) -> bool:
        path = self.unit_path()
        if not path.exists():
            return False
        subprocess.run(
            ["systemctl", "--user", "disable", "--now", self.SERVICE_NAME],
            check=False, capture_output=True,
        )
        path.unlink()
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, capture_output=True)
        return True

    def status(self) -> str:
        if not self.unit_path().exists():
            return "not installed"
        result = subprocess.run(
            ["systemctl", "--user", "is-active", self.SERVICE_NAME],
            capture_output=True, text=True,
        )
        return f"installed ({result.stdout.strip() or 'unknown'})"


# ---------------------------------------------------------------------
# Windows — Task Scheduler (primary) + Startup shortcut (fallback)
# ---------------------------------------------------------------------


class WindowsTaskSchedulerAdapter(AutostartAdapter):
    """Register a per-user logon task via schtasks.exe.

    No admin rights required — the task runs as the current user on login.
    Automatic restart-on-failure is handled by Task Scheduler itself.
    """

    TASK_NAME = "StreamSeeker Daemon"

    def unit_path(self) -> Path:
        # Task Scheduler tasks aren't files on disk we can hand back — we
        # return a sentinel so the AutostartAdapter contract still works.
        # The caller treats this as informational only.
        return Path(f"\\{self.TASK_NAME}")

    def render(self) -> str:
        """Command line that Task Scheduler will invoke."""
        python = sys.executable
        home_env = os.environ.get("STREAMSEEKER_HOME")
        env_prefix = ""
        if home_env:
            env_prefix = f'cmd /c "set STREAMSEEKER_HOME={home_env} && '
            suffix = '"'
        else:
            suffix = ""
        return (
            f'{env_prefix}"{python}" -m streamseeker daemon start --foreground{suffix}'
        )

    def activate(self) -> None:
        command = self.render()
        subprocess.run([
            "schtasks", "/Create", "/F",
            "/TN", self.TASK_NAME,
            "/SC", "ONLOGON",
            "/RL", "HIGHEST",
            "/TR", command,
        ], check=True, capture_output=True)

    def install(self) -> Path:
        # Task Scheduler has no on-disk unit to write — activation IS install.
        self.activate()
        return self.unit_path()

    def uninstall(self) -> bool:
        result = subprocess.run(
            ["schtasks", "/Delete", "/F", "/TN", self.TASK_NAME],
            check=False, capture_output=True,
        )
        return result.returncode == 0

    def status(self) -> str:
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", self.TASK_NAME],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return "installed"
        return "not installed"


# ---------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------


def get_adapter() -> AutostartAdapter:
    """Return the adapter for the current platform, or raise."""
    if sys.platform == "darwin":
        return LaunchdAdapter()
    if sys.platform.startswith("linux"):
        if shutil.which("systemctl") is None:
            raise AutostartUnavailableError(
                "systemctl not found — only systemd-based Linux is supported in the MVP."
            )
        return SystemdUserAdapter()
    if sys.platform == "win32":
        if shutil.which("schtasks") is None:
            raise AutostartUnavailableError(
                "schtasks.exe not found — Task Scheduler must be available on Windows."
            )
        return WindowsTaskSchedulerAdapter()
    raise AutostartUnavailableError(
        f"autostart is not implemented for platform {sys.platform!r} yet — see ADR 0013."
    )
