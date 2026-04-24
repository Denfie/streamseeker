from __future__ import annotations

from cleo.commands.command import Command

from streamseeker.distribution import desktop as desktop_icon


class UninstallDesktopIconCommand(Command):
    name = "uninstall-desktop-icon"
    description = "Remove the Desktop shortcut created by install-desktop-icon."

    def handle(self) -> int:
        removed = desktop_icon.uninstall()
        if not removed:
            self.line("<comment>No desktop icon found.</comment>")
            return 1
        self.line("<info>Removed:</info>")
        for path in removed:
            self.line(f"  {path}")
        return 0
