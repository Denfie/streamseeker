from __future__ import annotations

from cleo.commands.command import Command

from streamseeker.distribution import desktop as desktop_icon


class InstallDesktopIconCommand(Command):
    name = "install-desktop-icon"
    description = "Create a Desktop shortcut that opens the daemon dashboard."

    def handle(self) -> int:
        try:
            created = desktop_icon.install()
        except desktop_icon.DesktopIconUnavailableError as exc:
            self.line(f"<error>{exc}</error>")
            return 2
        except Exception as exc:
            self.line(f"<error>Failed to create desktop icon: {exc}</error>")
            return 3

        self.line("<info>Desktop icon(s) created:</info>")
        for path in created:
            self.line(f"  {path}")
        self.line(
            "\n<comment>Tip:</comment> make sure the daemon is running "
            "(<comment>streamseeker daemon start</comment>) so the icon "
            "actually opens something."
        )
        return 0
