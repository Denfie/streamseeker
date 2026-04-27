from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from cleo.commands.command import Command
from cleo.helpers import option

from streamseeker import paths
from streamseeker.distribution import (
    link_extension,
    source_extension_dir,
    sync_extension,
)


class InstallExtensionCommand(Command):
    name = "install-extension"
    description = (
        "Copy the browser extension to ~/.streamseeker/extension/ and open "
        "chrome://extensions/ so you can load it unpacked."
    )

    options = [
        option("update", None, "Overwrite an existing installation.", flag=True),
        option(
            "link",
            None,
            "Symlink the install dir to the source repo (developer mode — file edits go live).",
            flag=True,
        ),
        option("no-open", None, "Don't open the browser automatically.", flag=True),
    ]

    def handle(self) -> int:
        try:
            source_extension_dir()  # validates existence early
        except FileNotFoundError as exc:
            self.line(f"<error>{exc}</error>")
            return 2

        target = paths.extension_dir()

        if self.option("link"):
            try:
                target = link_extension()
            except OSError as exc:
                self.line(f"<error>Symlink failed: {exc}</error>")
                return 2
            self.line(
                f"<info>Extension linked (developer mode):</info> {target} "
                f"→ source repo"
            )
            self.line(
                "<comment>File edits in the repo are now live. Click 'Reload' "
                "in chrome://extensions/ after each change.</comment>"
            )
            if not self.option("no-open"):
                _open_extensions_page(self)
            self._print_install_instructions(target)
            return 0

        update = bool(self.option("update"))

        if target.exists() and not target.is_symlink() and not update:
            self.line(
                f"<comment>Extension already installed at {target}. "
                f"Re-run with --update to overwrite.</comment>"
            )
            return 1

        if target.is_symlink():
            self.line(
                f"<comment>{target} is a developer symlink — removing it "
                f"so the bundled copy can be installed.</comment>"
            )
            target.unlink()

        result = sync_extension(force=True)
        if result.action == "updated":
            self.line(
                f"<info>Extension updated:</info> "
                f"{result.installed_version} → {result.bundled_version}"
            )
        elif result.action == "installed":
            self.line(
                f"<info>Extension installed</info> (version {result.bundled_version})"
            )
        else:
            self.line(f"<info>Extension copied to:</info> {target}")

        if not self.option("no-open"):
            _open_extensions_page(self)

        self._print_install_instructions(target)
        if update:
            self.line(
                "\n<comment>Tip:</comment> reload the extension in chrome://extensions/ "
                "so Chrome picks up the new files (the extension also reloads "
                "itself when its background worker notices the disk version "
                "changed)."
            )
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
