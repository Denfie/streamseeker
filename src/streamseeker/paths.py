"""Central path resolution for all StreamSeeker runtime data.

Single source of truth — no other module should hardcode `"logs/…"` or
`"downloads/…"` paths. All user-specific data lives under a single root
directory, by default `~/.streamseeker/`, overridable via the
`STREAMSEEKER_HOME` environment variable.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_ENV_VAR = "STREAMSEEKER_HOME"
_DEFAULT_DIRNAME = ".streamseeker"


def home() -> Path:
    """Return the root data directory for StreamSeeker."""
    override = os.environ.get(_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / _DEFAULT_DIRNAME


def config_file() -> Path:
    return home() / "config.json"


def credentials_file() -> Path:
    return home() / "config.credentials.json"


def load_credentials() -> dict:
    """Return the credentials dict or {} if the file is missing/unreadable.

    Never raises — calling code should treat missing keys as "no credential".
    """
    file = credentials_file()
    if not file.is_file():
        return {}
    try:
        return json.loads(file.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def logs_dir() -> Path:
    return home() / "logs"


def queue_file() -> Path:
    return logs_dir() / "download_queue.json"


def daemon_pid_file() -> Path:
    return logs_dir() / "daemon.pid"


def daemon_log_file() -> Path:
    return logs_dir() / "daemon.log"


def daemon_err_file() -> Path:
    return logs_dir() / "daemon.err"


def unsupported_providers_file() -> Path:
    return logs_dir() / "unsupported_providers.json"


def filemoon_debug_file() -> Path:
    return logs_dir() / "filemoon_debug.json"


def library_dir() -> Path:
    return home() / "library"


def library_index_file() -> Path:
    return library_dir() / "index.json"


def favorites_dir() -> Path:
    return home() / "favorites"


def favorites_index_file() -> Path:
    return favorites_dir() / "index.json"


def extension_dir() -> Path:
    return home() / "extension"


def downloads_dir() -> Path:
    """Return the downloads directory.

    If `config.json` defines `output_folder`, that wins — it lets users keep
    media on an external drive while metadata stays under `~/.streamseeker/`.
    Absolute paths are honored as-is; relative paths resolve against `home()`.
    """
    cfg = config_file()
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text())
            folder = data.get("output_folder")
            if folder:
                path = Path(folder).expanduser()
                return path if path.is_absolute() else home() / path
        except (json.JSONDecodeError, OSError):
            pass
    return home() / "downloads"


def series_dir(kind: str, stream: str, slug: str) -> Path:
    """Return the asset directory for a single series under library/ or favorites/."""
    if kind == "library":
        root = library_dir()
    elif kind == "favorites":
        root = favorites_dir()
    else:
        raise ValueError(f"kind must be 'library' or 'favorites', got {kind!r}")
    return root / stream / slug


def series_file(kind: str, stream: str, slug: str) -> Path:
    """Return the JSON file for a single series."""
    return series_dir(kind, stream, slug).parent / f"{slug}.json"


def display_path(path) -> str:
    """Return ``path`` with the user home replaced by ``~`` for display/log output.

    Never touches real filesystem paths — only the string. Accepts ``str``,
    ``Path``, or anything castable to ``str``. Falls back to the input if it
    doesn't live under ``Path.home()``.
    """
    try:
        p = Path(str(path)).expanduser()
    except Exception:
        return str(path)
    try:
        home_dir = Path.home()
        abs_path = p.resolve() if p.is_absolute() else p
        rel = abs_path.relative_to(home_dir)
        return f"~/{rel.as_posix()}"
    except (ValueError, OSError):
        return str(path)


def expand_path(path: str) -> str:
    """Inverse of ``display_path`` — turn ``~/…`` back into an absolute path."""
    return str(Path(path).expanduser())


def ensure_runtime_dirs() -> None:
    """Create the core runtime directories if they don't exist yet.

    Safe to call repeatedly. Creates parents as needed.
    """
    for path in (logs_dir(), library_dir(), favorites_dir()):
        path.mkdir(parents=True, exist_ok=True)


def legacy_project_root() -> Path | None:
    """Return the old in-project data root if it looks like an old install.

    Used by the `migrate` command to detect pre-`~/.streamseeker/` layouts.
    Returns the project root path if either `./logs/download_queue.json` or
    `./config.json` exists relative to the current working directory.
    """
    cwd = Path.cwd()
    markers = [cwd / "logs" / "download_queue.json", cwd / "config.json"]
    if any(m.exists() for m in markers):
        return cwd
    return None
