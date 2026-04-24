from __future__ import annotations

import shutil

from cleo.commands.command import Command

from streamseeker import paths


class UninstallExtensionCommand(Command):
    name = "uninstall-extension"
    description = "Remove ~/.streamseeker/extension/ (you still need to remove the extension in Chrome manually)."

    def handle(self) -> int:
        target = paths.extension_dir()
        if not target.exists():
            self.line("<comment>No extension installed.</comment>")
            return 1
        shutil.rmtree(target)
        self.line(f"<info>Removed:</info> {target}")
        self.line(
            "<comment>Note:</comment> Chrome still lists the extension under "
            "chrome://extensions/. Remove it there manually."
        )
        return 0
