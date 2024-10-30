from __future__ import annotations

import subprocess

from typing import TYPE_CHECKING
from typing import Any
from typing import ClassVar

from cleo.helpers import argument
from cleo.helpers import option

from cleo.commands.command import Command

if TYPE_CHECKING:
    from collections.abc import Collection

    from cleo.io.inputs.argument import Argument
    from cleo.io.inputs.option import Option

class RunCommand(Command):
    name = "run"

    description = "Run Streamseeker to get the interactive mode."

    def handle(self) -> int:
        from streamseeker.utils._compat import metadata


        self.line(
            f"""\
<fg=magenta>------------------------------------------------------------------------
---------------------- Streamseeker - Interactive ----------------------
------------------------------------------------------------------------</>

<fg=blue>Version:</> {metadata.version("streamseeker")}
"""
        )

        self.choices: list[str] = [
                "Download a show",
                # "Search a show",
                "About us",
                "-- Quit --",
            ];

        search_type = self.choice(
            "What do you want to do?",
            self.choices,
            attempts=3,
            default=len(self.choices) - 1,
        )
        self.line("")

        match search_type:
            case "Search for a show":
                subprocess.call(['python', '-m', 'streamseeker', 'search'])
                return 0
            case "Download a show":
                subprocess.call(['python', '-m', 'streamseeker', 'download'])
            case "About us":
                subprocess.call(['python', '-m', 'streamseeker', 'about'])
            case "-- Quit --":
                return 0
            case _:
                self.line("Invalid choice")

        return 0

    