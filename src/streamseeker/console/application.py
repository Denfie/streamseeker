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

from streamseeker.console.command_loader import CommandLoader
from streamseeker.api.core.logger import Logger
from streamseeker.utils._compat import get_version

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
        # Python modules cannot contain hyphens; translate them to underscores
        # for the on-disk module name but preserve hyphens in the class name
        # (TitleCased, e.g. "install-autostart" -> "InstallAutostart").
        module_parts = [w.replace("-", "_") for w in words]
        module = import_module("streamseeker.console.commands." + ".".join(module_parts))
        class_name = "".join(
            "".join(segment.title() for segment in w.split("-")) for w in words
        ) + "Command"
        command_class = getattr(module, class_name)
        command: Command = command_class()
        return command

    return _load

COMMANDS = [
    "about",
    "run",
    "download",
    "retry",
    "migrate",
    "favorite add",
    "favorite remove",
    "favorite list",
    "favorite search",
    "favorite promote",
    "favorite refresh",
    "library list",
    "library search",
    "library show",
    "library stats",
    "library remove",
    "library refresh",
    "library rescan",
    "daemon start",
    "daemon stop",
    "daemon restart",
    "daemon status",
    "daemon logs",
    "daemon install-autostart",
    "daemon uninstall-autostart",
    "install-extension",
    "uninstall-extension",
    "install-desktop-icon",
    "uninstall-desktop-icon",
    "uninstall",
    # "search",
    # "version",
]

__version__ = get_version()

class Application(BaseApplication):
    def __init__(self) -> None:
        super().__init__("streamseeker", __version__)
        self._default_command = "run"

        self._streamseeker: Streamseeker | None = None
        self._io: IO | None = None
        self._disable_plugins = False
        self._disable_cache = False
        self._plugins_loaded = False

        command_loader = CommandLoader({name: load_command(name) for name in COMMANDS})
        self.set_command_loader(command_loader)

def main() -> int:
    from streamseeker.i18n import init_from_config
    init_from_config()
    exit_code: int = Application().run()
    return exit_code

if __name__ == "__main__":
    main()