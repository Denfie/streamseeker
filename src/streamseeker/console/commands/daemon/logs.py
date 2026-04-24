from __future__ import annotations

from cleo.commands.command import Command
from cleo.helpers import option

from streamseeker import paths


class DaemonLogsCommand(Command):
    name = "daemon logs"
    description = "Print the last lines of daemon.log (and daemon.err with --errors)."

    options = [
        option("lines", "n", "How many trailing lines to show (default 50).", flag=False, default="50"),
        option("errors", "e", "Show daemon.err instead of daemon.log.", flag=True),
    ]

    def handle(self) -> int:
        try:
            lines = int(self.option("lines") or 50)
        except (TypeError, ValueError):
            self.line("<error>--lines must be an integer.</error>")
            return 2

        file = paths.daemon_err_file() if self.option("errors") else paths.daemon_log_file()
        if not file.is_file():
            self.line(f"<comment>{file} does not exist — daemon hasn't written any logs yet.</comment>")
            return 0

        content = file.read_text().splitlines()
        tail = content[-lines:]
        if not tail:
            self.line("<comment>(empty)</comment>")
            return 0
        for line in tail:
            self.line(line)
        return 0
