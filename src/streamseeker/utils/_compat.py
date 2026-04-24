from __future__ import annotations

import locale
import sys

from contextlib import suppress


if sys.version_info < (3, 11):
    # compatibility for python <3.11
    import tomli as tomllib
else:
    import tomllib


if sys.version_info < (3, 10):
    # compatibility for python <3.10
    import importlib_metadata as metadata
else:
    from importlib import metadata

WINDOWS = sys.platform == "win32"


def decode(string: bytes | str, encodings: list[str] | None = None) -> str:
    if not isinstance(string, bytes):
        return string

    encodings = encodings or ["utf-8", "latin1", "ascii"]

    for encoding in encodings:
        with suppress(UnicodeEncodeError, UnicodeDecodeError):
            return string.decode(encoding)

    return string.decode(encodings[0], errors="ignore")


def encode(string: str, encodings: list[str] | None = None) -> bytes:
    if isinstance(string, bytes):
        return string

    encodings = encodings or ["utf-8", "latin1", "ascii"]

    for encoding in encodings:
        with suppress(UnicodeEncodeError, UnicodeDecodeError):
            return string.encode(encoding)

    return string.encode(encodings[0], errors="ignore")


def getencoding() -> str:
    if sys.version_info < (3, 11):
        return locale.getpreferredencoding()
    else:
        return locale.getencoding()


def get_version() -> str:
    """Return the installed package version.

    Primary source: ``importlib.metadata`` — works for every install mode
    (pipx, pip, poetry-shell, wheel). Fallback to reading ``pyproject.toml``
    next to the source tree so an uninstalled checkout still reports a
    version. Returns ``"0.0.0+unknown"`` if neither works — never raises,
    because a missing version must not break CLI startup.
    """
    try:
        return metadata.version("streamseeker")
    except metadata.PackageNotFoundError:
        pass

    try:
        from pathlib import Path

        pyproject_path = Path(__file__).resolve().parents[3] / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        # PEP 621 ``[project]``; keep legacy ``[tool.poetry]`` fallback so
        # an older local checkout still boots.
        project = data.get("project") or {}
        if project.get("version"):
            return project["version"]
        return data["tool"]["poetry"]["version"]
    except (FileNotFoundError, KeyError, OSError):
        return "0.0.0+unknown"


__all__ = [
    "WINDOWS",
    "decode",
    "encode",
    "get_version",
    "getencoding",
    "metadata",
    "tomllib",
]