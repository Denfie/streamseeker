from __future__ import annotations

from contextlib import suppress
from functools import cached_property
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING
from typing import cast

from cleo.commands.command import Command
from cleo.application import Application as BaseApplication
from cleo.events.console_command_event import ConsoleCommandEvent
from cleo.events.console_events import COMMAND
from cleo.events.event_dispatcher import EventDispatcher
from cleo.exceptions import CleoError
from cleo.formatters.style import Style
from cleo.io.null_io import NullIO

from streamseeker.__version__ import __version__
from streamseeker.console.command_loader import CommandLoader
from streamseeker.api.core.logger import Logger

if TYPE_CHECKING:
    from collections.abc import Callable

    from cleo.events.event import Event
    from cleo.io.inputs.argv_input import ArgvInput
    from cleo.io.inputs.definition import Definition
    from cleo.io.inputs.input import Input
    from cleo.io.io import IO
    from cleo.io.outputs.output import Output

    from streamseeker.streamseeker import Streamseeker

def load_command(name: str) -> Callable[[], Command]:
    def _load() -> Command:
        words = name.split(" ")
        module = import_module("streamseeker.console.commands." + ".".join(words))
        command_class = getattr(module, "".join(c.title() for c in words) + "Command")
        command: Command = command_class()
        return command

    return _load

COMMANDS = [
    "about",
    "run",
    "download",
    # "search",
    # "version",
]

class Application(BaseApplication):
    def __init__(self) -> None:
        super().__init__("streamseeker", __version__)

        self._streamseeker: Streamseeker | None = None
        self._io: IO | None = None
        self._disable_plugins = False
        self._disable_cache = False
        self._plugins_loaded = False

        command_loader = CommandLoader({name: load_command(name) for name in COMMANDS})
        self.set_command_loader(command_loader)

def main() -> int:
    exit_code: int = Application().run()
    return exit_code

if __name__ == "__main__":
    main()