from __future__ import annotations

import shutil

from cleo.commands.command import Command
from cleo.helpers import option

from streamseeker import paths
from streamseeker.daemon import lifecycle
from streamseeker.daemon.autostart import AutostartUnavailableError, get_adapter
from streamseeker.distribution import desktop as desktop_icon


class UninstallCommand(Command):
    name = "uninstall"
    description = (
        "Remove autostart, desktop icon and extension in one go. "
        "Pass --purge to also delete ~/.streamseeker/ (user data!)."
    )

    options = [
        option("purge", None, "Also delete ~/.streamseeker/ (destructive!).", flag=True),
        option("force", None, "Don't prompt for confirmation (implies --purge if set).", flag=True),
    ]

    def handle(self) -> int:
        purge = bool(self.option("purge"))
        force = bool(self.option("force"))

        self.line("<info>StreamSeeker — full uninstall</info>")
        self.line("This will:")
        self.line("  1. Stop the daemon if it's running")
        self.line("  2. Remove the autostart registration (LaunchAgent / systemd / Task Scheduler)")
        self.line("  3. Remove the Desktop shortcut")
        self.line("  4. Remove ~/.streamseeker/extension/")
        if purge:
            self.line(f"  5. <error>Delete all user data under {paths.home()}</error>")
        self.line("")

        if not force and not self.confirm("Proceed?", default=False):
            self.line("<comment>Aborted.</comment>")
            return 1

        self._stop_daemon()
        self._remove_autostart()
        self._remove_desktop_icon()
        self._remove_extension()

        if purge:
            self._purge_home(force)

        self.line("\n<info>Uninstall complete.</info>")
        return 0

    def _stop_daemon(self) -> None:
        if lifecycle.is_running():
            if lifecycle.stop():
                self.line("  <info>✓</info> daemon stopped")
            else:
                self.line("  <comment>!</comment> could not stop the daemon")
        else:
            self.line("  <comment>-</comment> daemon was not running")

    def _remove_autostart(self) -> None:
        try:
            adapter = get_adapter()
        except AutostartUnavailableError:
            self.line("  <comment>-</comment> no autostart support on this platform")
            return
        if adapter.uninstall():
            self.line("  <info>✓</info> autostart removed")
        else:
            self.line("  <comment>-</comment> autostart was not installed")

    def _remove_desktop_icon(self) -> None:
        removed = desktop_icon.uninstall()
        if removed:
            self.line(f"  <info>✓</info> desktop icon removed ({len(removed)})")
        else:
            self.line("  <comment>-</comment> no desktop icon")

    def _remove_extension(self) -> None:
        target = paths.extension_dir()
        if target.exists():
            shutil.rmtree(target)
            self.line("  <info>✓</info> extension folder removed")
            self.line("      (remember to remove it in chrome://extensions/ too)")
        else:
            self.line("  <comment>-</comment> no extension folder")

    def _purge_home(self, force: bool) -> None:
        home = paths.home()
        if not home.exists():
            self.line("  <comment>-</comment> ~/.streamseeker/ does not exist")
            return
        if not force:
            if not self.confirm(
                f"Really delete {home} and everything inside it?",
                default=False,
            ):
                self.line("  <comment>-</comment> purge skipped")
                return
        shutil.rmtree(home)
        self.line(f"  <info>✓</info> removed {home}")
