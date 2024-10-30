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

    # arguments: ClassVar[list[Argument]] = [
    #     argument("name", "The packages to add.", multiple=True)
    # ]
    options: ClassVar[list[Option]] = [
        option(
            "dev",
            "D",
            "Add as a development dependency. (shortcut for '-G dev')",
        ),
        option("editable", "e", "Add vcs/path dependencies as editable."),
        option(
            "extras",
            "E",
            "Extras to activate for the dependency.",
            flag=False,
            multiple=True,
        ),
        option(
            "optional",
            None,
            "Add as an optional dependency to an extra.",
            flag=False,
        ),
        option(
            "python",
            None,
            "Python version for which the dependency must be installed.",
            flag=False,
        ),
        option(
            "platform",
            None,
            "Platforms for which the dependency must be installed.",
            flag=False,
        ),
        option(
            "source",
            None,
            "Name of the source to use to install the package.",
            flag=False,
        ),
        option("allow-prereleases", None, "Accept prereleases."),
        option(
            "dry-run",
            None,
            "Output the operations but do not execute anything (implicitly enables"
            " --verbose).",
        ),
        option("lock", None, "Do not perform operations (only update the lockfile)."),
    ]

    examples = """\
If you do not specify a version constraint, poetry will choose a suitable one based on\
 the available package versions.

You can specify a package in the following forms:
  - A single name (<b>requests</b>)
  - A name and a constraint (<b>requests@^2.23.0</b>)
  - A git url (<b>git+https://github.com/python-poetry/poetry.git</b>)
  - A git url with a revision\
 (<b>git+https://github.com/python-poetry/poetry.git#develop</b>)
  - A subdirectory of a git repository\
 (<b>git+https://github.com/python-poetry/poetry.git#subdirectory=tests/fixtures/sample_project</b>)
  - A git SSH url (<b>git+ssh://github.com/python-poetry/poetry.git</b>)
  - A git SSH url with a revision\
 (<b>git+ssh://github.com/python-poetry/poetry.git#develop</b>)
  - A file path (<b>../my-package/my-package.whl</b>)
  - A directory (<b>../my-package/</b>)
  - A url (<b>https://example.com/packages/my-package-0.1.0.tar.gz</b>)
"""
    help = f"""\
The add command adds required packages to your <comment>pyproject.toml</> and installs\
 them.

{examples}
"""
    loggers: ClassVar[list[str]] = [
        "poetry.repositories.pypi_repository",
        "poetry.inspection.info",
    ]

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

    