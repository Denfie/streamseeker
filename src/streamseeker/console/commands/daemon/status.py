from __future__ import annotations

from cleo.commands.command import Command

from streamseeker.daemon import lifecycle


class DaemonStatusCommand(Command):
    name = "daemon status"
    description = "Show whether the daemon is running and on which port."

    def handle(self) -> int:
        info = lifecycle.describe()
        if info["running"]:
            self.line(
                f"<info>Running</info> — pid {info['pid']}, "
                f"http://{info['host']}:{info['port']}"
            )
            self.line(f"  PID file: <comment>{info['pid_file']}</comment>")
            return 0
        self.line("<comment>Daemon is not running.</comment>")
        self.line(f"  PID file: {info['pid_file']}")
        return 1
