from __future__ import annotations

import streamseeker
import subprocess

from cleo.commands.command import Command

class RunCommand(Command):
    name = "run"

    description = "Run Streamseeker to get the interactive mode."

    def handle(self) -> int:
        from streamseeker.utils._compat import metadata
        __version__ = metadata.version("streamseeker")
        __version__ = "0.1.5"

        self.line(
            f"""\
<fg=magenta>------------------------------------------------------------------------
---------------------- Streamseeker - Interactive ----------------------
------------------------------------------------------------------------</>

Version: <fg=cyan>{__version__}</>
"""
        )

        self.choices: list[str] = [
                "Download a movie or show",
                # "Search a movie or show",
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
            case "Search a movie or show":
                subprocess.call(['python', '-m', 'streamseeker', 'search'])
                return 0
            case "Download a movie or show":
                subprocess.call(['python', '-m', 'streamseeker', 'download'])
            case "About us":
                subprocess.call(['python', '-m', 'streamseeker', 'about'])
            case "-- Quit --":
                return 0
            case _:
                self.line("Invalid choice")

        return 0

    