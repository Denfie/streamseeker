from __future__ import annotations

from cleo.commands.command import Command

class AboutCommand(Command):
    name = "about"

    description = "Shows information about Streamseeker."

    def handle(self) -> int:
        from streamseeker.utils._compat import get_version

        self.line(
            f"""\
<info>Streamseeker - Download library for streaming sites written in python</info>

Version: <info>{get_version()}</info>

<comment>Streamseeker works currently with <fg=blue>AniWorld</> and <fg=blue>Serien Stream</>.
See <fg=blue>https://github.com/uniprank/streamseeker</> for more information.</comment>\
"""
        )

        return 0