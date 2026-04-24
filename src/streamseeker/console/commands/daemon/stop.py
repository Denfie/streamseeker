from __future__ import annotations

from cleo.commands.command import Command

from streamseeker.daemon import lifecycle


class DaemonStopCommand(Command):
    name = "daemon stop"
    description = "Stop the running daemon."

    def handle(self) -> int:
        if lifecycle.stop():
            self.line("<info>Daemon stopped.</info>")
            return 0
        self.line("<comment>No daemon was running.</comment>")
        return 1
