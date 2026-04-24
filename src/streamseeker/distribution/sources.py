"""Locate the source Extension / icon assets that ship with the CLI.

In the MVP we ship from the git checkout: resolve paths relative to
``src/streamseeker/``'s parent package roots. When we ever wheel-package
the extension as ``package_data``, this is the single place to switch.
"""

from __future__ import annotations

from pathlib import Path

import streamseeker


class SourceAssetMissingError(FileNotFoundError):
    """Raised when an expected source asset can't be located."""


def _repo_root() -> Path:
    """Return the git-checkout root that contains ``extension/``.

    Walks up from ``streamseeker.__file__`` looking for the ``extension``
    directory. Works for editable installs (``pip install -e .``) and for
    "running from the repo" (``python -m streamseeker``).
    """
    cur = Path(streamseeker.__file__).resolve().parent
    for _ in range(6):
        if (cur / "extension" / "manifest.json").is_file():
            return cur
        cur = cur.parent
    raise SourceAssetMissingError(
        "Could not find the 'extension/' folder — StreamSeeker is installed "
        "in a way that doesn't ship the browser extension. Check out the "
        "git repository to use `install-extension`."
    )


def source_extension_dir() -> Path:
    """Return the checkout's ``extension/`` directory (source of truth)."""
    return _repo_root() / "extension"


def source_master_icon() -> Path:
    """Return the master app-icon SVG used by `make icons` and install-desktop-icon."""
    path = _repo_root() / "extension" / "icons" / "streamseeker-master.svg"
    if not path.is_file():
        raise SourceAssetMissingError(f"master icon missing: {path}")
    return path
