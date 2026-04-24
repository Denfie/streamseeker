from __future__ import annotations

from cleo.commands.command import Command

from streamseeker.daemon.autostart import AutostartUnavailableError, get_adapter


class DaemonUninstallAutostartCommand(Command):
    name = "daemon uninstall-autostart"
    description = "Remove the autostart registration for the daemon."

    def handle(self) -> int:
        try:
            adapter = get_adapter()
        except AutostartUnavailableError as exc:
            self.line(f"<error>{exc}</error>")
            return 2

        removed = adapter.uninstall()
        if removed:
            self.line("<info>Autostart removed.</info>")
            return 0
        self.line("<comment>Autostart was not installed.</comment>")
        return 1
