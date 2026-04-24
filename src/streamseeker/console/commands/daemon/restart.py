from __future__ import annotations

from cleo.commands.command import Command
from cleo.helpers import option

from streamseeker.daemon import lifecycle
from streamseeker.daemon.lifecycle import DaemonAlreadyRunningError


class DaemonRestartCommand(Command):
    name = "daemon restart"
    description = "Stop the daemon (if running) and start it again."

    options = [
        option(
            "foreground",
            "f",
            "Run in the foreground (blocks). Used by LaunchAgent/systemd.",
            flag=True,
        ),
    ]

    def handle(self) -> int:
        if lifecycle.is_running():
            if lifecycle.stop():
                self.line("<info>Daemon stopped.</info>")
            else:
                self.line("<error>Could not stop the running daemon.</error>")
                return 1
        else:
            self.line("<comment>No daemon was running — starting fresh.</comment>")

        foreground = bool(self.option("foreground"))
        try:
            result = lifecycle.start(foreground=foreground)
        except DaemonAlreadyRunningError as exc:
            self.line(f"<comment>Daemon already running (pid={exc.pid}).</comment>")
            return 1
        except OSError as exc:
            self.line(f"<error>{exc}</error>")
            return 2

        if foreground:
            self.line("<info>Daemon stopped.</info>")
            return 0

        if result.running and result.pid:
            self.line(
                f"<info>Daemon restarted</info> — pid {result.pid} "
                f"listening on http://{result.host}:{result.port}"
            )
            return 0

        self.line("<error>Daemon restart failed — check ~/.streamseeker/logs/daemon.err</error>")
        return 2
