from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from cleo.commands.command import Command
from cleo.helpers import option

from streamseeker import paths
from streamseeker.distribution import source_extension_dir


class InstallExtensionCommand(Command):
    name = "install-extension"
    description = (
        "Copy the browser extension to ~/.streamseeker/extension/ and open "
        "chrome://extensions/ so you can load it unpacked."
    )

    options = [
        option("update", None, "Overwrite an existing installation.", flag=True),
        option("no-open", None, "Don't open the browser automatically.", flag=True),
    ]

    def handle(self) -> int:
        try:
            src = source_extension_dir()
        except FileNotFoundError as exc:
            self.line(f"<error>{exc}</error>")
            return 2

        target = paths.extension_dir()
        update = bool(self.option("update"))

        if target.exists():
            if not update:
                self.line(
                    f"<comment>Extension already installed at {target}. "
                    f"Re-run with --update to overwrite.</comment>"
                )
                return 1
            shutil.rmtree(target)

        shutil.copytree(src, target)
        self.line(f"<info>Extension copied to:</info> {target}")

        if not self.option("no-open"):
            _open_extensions_page(self)

        self._print_install_instructions(target)
        if update:
            self.line("\n<comment>Tip:</comment> reload the extension in chrome://extensions/ "
                      "so Chrome picks up the new files.")
        return 0

    def _print_install_instructions(self, target: Path) -> None:
        self.line("\n<info>Next steps:</info>")
        self.line("  1. In Chrome, toggle <comment>Developer Mode</comment> (top right).")
        self.line("  2. Click <comment>Load Unpacked</comment>.")
        self.line(f"  3. Select the folder: <comment>{target}</comment>")
        self.line("  4. Visit an aniworld.to / s.to / megakino.tax page to see the badges.\n")
        self.line("Make sure the daemon is running:")
        self.line("  <comment>streamseeker daemon start</comment>")


def _open_extensions_page(cmd: Command) -> None:
    """Best-effort open of chrome://extensions/ using the platform's URL handler."""
    url = "chrome://extensions/"
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", "-a", "Google Chrome", url], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", url], check=False)
        elif sys.platform == "win32":
            subprocess.run(["cmd", "/c", "start", url], check=False, shell=False)
        else:
            cmd.line(f"<comment>Open manually: {url}</comment>")
    except Exception:
        cmd.line(f"<comment>Couldn't open the browser automatically. Visit: {url}</comment>")
