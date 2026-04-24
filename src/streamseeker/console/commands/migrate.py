from __future__ import annotations

import shutil
from pathlib import Path

from cleo.commands.command import Command
from cleo.helpers import option

from streamseeker import paths


# Names of things that move from the old project-relative layout to ~/.streamseeker/.
# Each entry: (source_path_relative_to_project_root, target_absolute_path_callable)
_MIGRATABLE: list[tuple[str, callable]] = [
    ("logs", lambda: paths.home() / "logs"),
    ("downloads", lambda: paths.home() / "downloads"),
    ("config.json", paths.config_file),
    ("config.credentials.json", paths.credentials_file),
]


class MigrateCommand(Command):
    name = "migrate"
    description = "Move user data from the old project-local layout to ~/.streamseeker/."

    options = [
        option("dry-run", None, "Only show what would move, don't touch anything.", flag=True),
        option("force", None, "Skip the confirmation prompt.", flag=True),
    ]

    def handle(self) -> int:
        project_root = paths.legacy_project_root()
        if project_root is None:
            self.line("<info>No legacy data detected in the current directory — nothing to migrate.</info>")
            return 0

        home = paths.home()
        self.line(f"<comment>Legacy data found at:</comment> {project_root}")
        self.line(f"<comment>Target root:</comment>          {home}")
        self.line("")

        plan = self._plan(project_root)
        if not plan:
            self.line("<info>Nothing to move — all items are either missing or already present at the target.</info>")
            return 0

        self.line("<info>Planned moves:</info>")
        for source, target, note in plan:
            marker = "[skip]" if note else "[move]"
            line = f"  {marker} {source}  →  {target}"
            if note:
                line += f"  <comment>({note})</comment>"
            self.line(line)

        if self.option("dry-run"):
            self.line("\n<comment>Dry run — nothing was moved.</comment>")
            return 0

        if not self.option("force"):
            if not self.confirm("\nProceed with the moves listed above?", default=False):
                self.line("<comment>Aborted.</comment>")
                return 1

        home.mkdir(parents=True, exist_ok=True)
        moved = 0
        for source, target, note in plan:
            if note:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            moved += 1
            self.line(f"  <info>moved</info> {source.name}")

        self.line(f"\n<info>Done — {moved} item(s) moved to {home}.</info>")
        return 0

    def _plan(self, project_root: Path) -> list[tuple[Path, Path, str]]:
        """Build the list of (source, target, skip_reason) tuples.

        An empty skip_reason means the item will be moved.
        """
        plan: list[tuple[Path, Path, str]] = []
        for rel, target_fn in _MIGRATABLE:
            source = project_root / rel
            target = target_fn()
            if not source.exists():
                continue  # nothing to move, don't show in plan
            if target.exists():
                plan.append((source, target, "target already exists"))
            else:
                plan.append((source, target, ""))
        return plan
