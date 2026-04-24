"""Create a Desktop-level shortcut that opens the daemon dashboard.

ADR 0014: the icon always opens ``http://127.0.0.1:8765/``. Per platform:

- **macOS**: ``~/Desktop/StreamSeeker.command`` — a tiny shell script that
  calls ``open``. Fallback when no ``.app`` bundle exists.
- **Linux**: ``~/.local/share/applications/streamseeker.desktop`` plus a
  symlink to ``~/Desktop/`` if the Desktop dir exists.
- **Windows**: ``%USERPROFILE%\\Desktop\\StreamSeeker.lnk`` created via a
  PowerShell one-liner (no ``pywin32`` dependency).
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

DAEMON_URL = "http://127.0.0.1:8765/"


class DesktopIconUnavailableError(RuntimeError):
    pass


def install() -> list[Path]:
    """Create the desktop shortcut(s). Returns the paths that were created."""
    if sys.platform == "darwin":
        return [_install_macos()]
    if sys.platform.startswith("linux"):
        return _install_linux()
    if sys.platform == "win32":
        return [_install_windows()]
    raise DesktopIconUnavailableError(
        f"Desktop icon not implemented for platform {sys.platform!r}."
    )


def uninstall() -> list[Path]:
    """Remove the desktop shortcut(s). Returns the paths that were removed."""
    removed: list[Path] = []
    for candidate in _candidates():
        if candidate.exists() or candidate.is_symlink():
            candidate.unlink()
            removed.append(candidate)
    return removed


def _candidates() -> list[Path]:
    home = Path.home()
    return [
        home / "Desktop" / "StreamSeeker.command",
        home / "Desktop" / "streamseeker.desktop",
        home / ".local" / "share" / "applications" / "streamseeker.desktop",
        home / "Desktop" / "StreamSeeker.lnk",
    ]


# ---------------------------------------------------------------------
# macOS
# ---------------------------------------------------------------------


def _install_macos() -> Path:
    target = Path.home() / "Desktop" / "StreamSeeker.command"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "#!/bin/bash\n"
        "# StreamSeeker dashboard launcher\n"
        f'open "{DAEMON_URL}"\n'
    )
    target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return target


# ---------------------------------------------------------------------
# Linux
# ---------------------------------------------------------------------


def _install_linux() -> list[Path]:
    apps_dir = Path.home() / ".local" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    desktop_file = apps_dir / "streamseeker.desktop"
    desktop_file.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=StreamSeeker\n"
        "Comment=Open the StreamSeeker dashboard\n"
        f"Exec=xdg-open {DAEMON_URL}\n"
        "Icon=streamseeker\n"
        "Terminal=false\n"
        "Categories=Network;AudioVideo;\n"
    )
    desktop_file.chmod(0o755)

    created = [desktop_file]
    desktop_dir = Path.home() / "Desktop"
    if desktop_dir.is_dir():
        link = desktop_dir / "streamseeker.desktop"
        if link.exists() or link.is_symlink():
            link.unlink()
        os.symlink(desktop_file, link)
        created.append(link)
    return created


# ---------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------


def _install_windows() -> Path:
    userprofile = os.environ.get("USERPROFILE") or str(Path.home())
    target = Path(userprofile) / "Desktop" / "StreamSeeker.lnk"
    target.parent.mkdir(parents=True, exist_ok=True)

    # PowerShell one-liner: creates a .lnk that opens the dashboard URL.
    ps = (
        f'$w=New-Object -ComObject WScript.Shell;'
        f'$s=$w.CreateShortcut("{target}");'
        f'$s.TargetPath="{DAEMON_URL}";'
        f'$s.IconLocation="shell32.dll,220";'
        f'$s.Save()'
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   check=True, capture_output=True)
    return target
