from __future__ import annotations

import sys

from cleo.commands.command import Command

from streamseeker.daemon.autostart import AutostartUnavailableError, get_adapter


class DaemonInstallAutostartCommand(Command):
    name = "daemon install-autostart"
    description = "Register the daemon to start automatically on login."

    def handle(self) -> int:
        try:
            adapter = get_adapter()
        except AutostartUnavailableError as exc:
            self.line(f"<error>{exc}</error>")
            return 2

        try:
            path = adapter.install()
        except Exception as exc:
            self.line(f"<error>Failed to install autostart: {exc}</error>")
            return 3

        self.line(f"<info>Autostart installed:</info> {path}")
        self.line(f"  Status: {adapter.status()}")
        if sys.platform.startswith("linux"):
            self.line(
                "  <comment>Tip:</comment> for start-without-login, run once: "
                "loginctl enable-linger $USER"
            )
        return 0
