"""Tiny in-process i18n for StreamSeeker.

Strings are stored as flat JSON dicts (one per language) under
``streamseeker.locales``. Active language is set once at startup from
``config.json`` (or ``en`` if missing/unknown). Any string the active
locale doesn't carry falls back to the English bundle, then to the
key itself — so a missing translation never crashes a code path.

Usage:

    from streamseeker.i18n import set_language, t
    set_language("de")
    print(t("queue.added", count=3))   # "3 Einträge zur Sammlung hinzugefügt."

Strings can carry ``{name}``-style placeholders that are filled in via
``str.format(**kwargs)``. Keep the placeholder set identical across
locales — the test suite verifies that.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

SUPPORTED_LANGUAGES: tuple[str, ...] = ("de", "en")
DEFAULT_LANGUAGE = "en"

_active_language: str = DEFAULT_LANGUAGE
_bundles: dict[str, dict[str, str]] = {}


def _load_bundle(code: str) -> dict[str, str]:
    """Read ``locales/<code>.json`` from the package. Empty on failure."""
    if code in _bundles:
        return _bundles[code]
    try:
        text = resources.files("streamseeker.locales").joinpath(f"{code}.json").read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            data = {}
    except (FileNotFoundError, ModuleNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    _bundles[code] = data
    return data


def set_language(code: str | None) -> str:
    """Switch the active language. Falls back to ``DEFAULT_LANGUAGE`` for
    unknown codes. Returns the code that ended up active.
    """
    global _active_language
    if code in SUPPORTED_LANGUAGES:
        _active_language = code  # type: ignore[assignment]
    else:
        _active_language = DEFAULT_LANGUAGE
    _load_bundle(_active_language)
    if _active_language != DEFAULT_LANGUAGE:
        _load_bundle(DEFAULT_LANGUAGE)
    return _active_language


def get_language() -> str:
    return _active_language


def t(key: str, /, **kwargs: Any) -> str:
    """Translate ``key`` to the active language.

    Lookup order: active locale → English fallback → the key itself.
    ``kwargs`` are applied via ``str.format`` so callers can inline
    placeholders — missing placeholders raise ``KeyError`` (a bug, not
    a translation issue, so failing loud is fine).
    """
    bundle = _bundles.get(_active_language) or _load_bundle(_active_language)
    fallback = _bundles.get(DEFAULT_LANGUAGE) or _load_bundle(DEFAULT_LANGUAGE)
    raw = bundle.get(key) or fallback.get(key) or key
    if not kwargs:
        return raw
    try:
        return raw.format(**kwargs)
    except (KeyError, IndexError):
        return raw


def init_from_config() -> str:
    """Read ``language`` from ``config.json`` and activate it.

    Best-effort — if config is missing or unreadable, default English
    stays active. Called from the CLI/daemon entry points.
    """
    from streamseeker import paths
    cfg_file = paths.config_file()
    if cfg_file.is_file():
        try:
            cfg = json.loads(cfg_file.read_text())
            return set_language(cfg.get("language"))
        except (json.JSONDecodeError, OSError):
            pass
    return set_language(DEFAULT_LANGUAGE)


__all__ = [
    "SUPPORTED_LANGUAGES",
    "DEFAULT_LANGUAGE",
    "set_language",
    "get_language",
    "t",
    "init_from_config",
]
