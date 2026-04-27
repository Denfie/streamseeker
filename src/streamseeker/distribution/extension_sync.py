"""Auto-sync the bundled browser extension to ``~/.streamseeker/extension/``.

Goal: a CLI upgrade should bring the browser extension along with it without
the user having to remember ``streamseeker install-extension --update``. The
daemon calls :func:`sync_extension` at startup; the function:

1. Reads the version from the bundled (source) ``manifest.json``.
2. Reads the version of the currently installed copy.
3. Replaces the install with the bundled copy when the bundled version is
   newer (semver) than the installed one.

The symlink case is honoured carefully — when ``~/.streamseeker/extension`` is
a symlink (developer mode created via ``install-extension --link``), we don't
clobber it.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from streamseeker import paths
from streamseeker.distribution.sources import (
    SourceAssetMissingError,
    source_extension_dir,
)


@dataclass(frozen=True)
class SyncResult:
    """Outcome of a sync attempt — used by the daemon log + tests."""

    bundled_version: str | None
    installed_version: str | None
    action: str  # "updated" | "in_sync" | "installed" | "skipped_symlink" | "no_source"
    target: Path

    @property
    def changed(self) -> bool:
        return self.action in ("updated", "installed")


def _parse_version(text: str) -> tuple[int, ...]:
    """Parse a SemVer string into a comparable tuple. Falls back to (0,)."""
    out: list[int] = []
    for part in text.split("."):
        digits = "".join(c for c in part if c.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out) or (0,)


def _read_manifest_version(manifest_path: Path) -> str | None:
    if not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    version = data.get("version")
    return version if isinstance(version, str) else None


def _atomic_replace(src: Path, dst: Path) -> None:
    """Replace ``dst`` with a fresh copy of ``src`` atomically.

    Strategy: copy to a sibling temp dir, then rename old → ``.bak`` and
    temp → final, then drop ``.bak``. If anything fails before the final
    rename, the existing install stays intact.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".extension-sync-", dir=str(dst.parent)))
    staged = tmp / "extension"
    try:
        shutil.copytree(src, staged)
        backup = dst.with_suffix(".bak")
        if backup.exists():
            shutil.rmtree(backup)
        if dst.exists():
            dst.rename(backup)
        staged.rename(dst)
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


def sync_extension(*, force: bool = False) -> SyncResult:
    """Bring ``~/.streamseeker/extension`` in line with the bundled source.

    Returns a :class:`SyncResult` describing what happened. Never raises for
    "expected" failures (no source, symlink in place, equal versions) — the
    daemon shouldn't crash because of an extension hiccup.

    With ``force=True`` the installed copy is replaced even when versions
    match — useful for the ``install-extension --update`` command.
    """
    target = paths.extension_dir()

    # Don't touch a developer-mode symlink: the developer wants live edits.
    if target.is_symlink():
        return SyncResult(
            bundled_version=None,
            installed_version=_read_manifest_version(target / "manifest.json"),
            action="skipped_symlink",
            target=target,
        )

    try:
        src = source_extension_dir()
    except SourceAssetMissingError:
        return SyncResult(
            bundled_version=None,
            installed_version=_read_manifest_version(target / "manifest.json"),
            action="no_source",
            target=target,
        )

    bundled_version = _read_manifest_version(src / "manifest.json")
    installed_version = _read_manifest_version(target / "manifest.json")

    is_newer = (
        bundled_version is not None
        and (
            installed_version is None
            or _parse_version(bundled_version) > _parse_version(installed_version)
        )
    )

    if not target.exists():
        _atomic_replace(src, target)
        return SyncResult(
            bundled_version=bundled_version,
            installed_version=None,
            action="installed",
            target=target,
        )

    if is_newer or force:
        _atomic_replace(src, target)
        return SyncResult(
            bundled_version=bundled_version,
            installed_version=installed_version,
            action="updated",
            target=target,
        )

    return SyncResult(
        bundled_version=bundled_version,
        installed_version=installed_version,
        action="in_sync",
        target=target,
    )


def installed_extension_version() -> str | None:
    """Return the version string of the currently installed extension, if any."""
    target = paths.extension_dir()
    return _read_manifest_version(target / "manifest.json")


def link_extension(source: Path | None = None) -> Path:
    """Create a symlink from ``~/.streamseeker/extension`` to the source dir.

    Used by ``streamseeker install-extension --link`` for development. Removes
    any pre-existing target (file, directory, or stale link). Returns the
    symlink path.
    """
    src = (source or source_extension_dir()).resolve()
    target = paths.extension_dir()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() or target.exists():
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()
    target.symlink_to(src, target_is_directory=True)
    return target


__all__: Iterable[str] = (
    "SyncResult",
    "sync_extension",
    "installed_extension_version",
    "link_extension",
)
