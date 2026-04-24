from __future__ import annotations

from cleo.commands.command import Command
from cleo.helpers import option

from streamseeker.daemon import lifecycle


class DaemonStartCommand(Command):
    name = "daemon start"
    description = "Start the background daemon (FastAPI on 127.0.0.1:8765)."

    options = [
        option(
            "foreground",
            "f",
            "Run in the foreground (blocks). Used by LaunchAgent/systemd.",
            flag=True,
        ),
    ]

    def handle(self) -> int:
        foreground = bool(self.option("foreground"))
        try:
            result = lifecycle.start(foreground=foreground)
        except lifecycle.DaemonAlreadyRunningError as exc:
            self.line(f"<comment>Daemon already running (pid={exc.pid}).</comment>")
            return 1
        except OSError as exc:
            self.line(f"<error>{exc}</error>")
            return 2

        if foreground:
            # Only reached after graceful shutdown
            self.line("<info>Daemon stopped.</info>")
            return 0

        if result.running and result.pid:
            self.line(
                f"<info>Daemon started</info> — pid {result.pid} "
                f"listening on http://{result.host}:{result.port}"
            )
            return 0

        self.line("<error>Daemon start failed — check ~/.streamseeker/logs/daemon.err</error>")
        return 2
