"""Provider registry + stream→chain mapping for metadata enrichment.

Each stream has an ordered chain of providers it tries. The first one that
returns a match "wins" for the main display, but every successful lookup is
stored under ``external.<provider>`` so the popup can render data from
multiple sources side-by-side (e.g. TMDb rating + AniList studios).

Chain config lives in ``~/.streamseeker/config.json``::

    {
      "metadata_chains": {
        "aniworldto": ["anilist", "tmdb"],
        "sto":        ["tvdb", "tmdb"],
        "megakinotax": ["tmdb"]
      }
    }

If a stream isn't listed, we fall back to the hard-coded defaults below.
"""

from __future__ import annotations

import json

from streamseeker import paths
from streamseeker.api.core.metadata.anilist import AniListProvider
from streamseeker.api.core.metadata.base import (
    MetadataProvider,
    MetadataUnavailableError,
)
from streamseeker.api.core.metadata.jikan import JikanProvider
from streamseeker.api.core.metadata.tmdb import TmdbProvider
from streamseeker.api.core.metadata.tvmaze import TvmazeProvider


# Factory per provider-name. A factory lazily builds the client and may raise
# MetadataUnavailableError when credentials/deps are missing — the resolver
# silently skips such providers.
_FACTORIES: dict[str, callable] = {
    "tmdb": TmdbProvider,
    "anilist": AniListProvider,
    "tvmaze": TvmazeProvider,
    "jikan": JikanProvider,
}

# Fallback-chains used when config.json doesn't pin something more specific.
# Order matters: first hit owns the artwork; later providers only contribute
# data blocks. TMDb provides FSK/USK, so we keep it in every chain.
_DEFAULT_CHAINS: dict[str, list[str]] = {
    "aniworldto": ["anilist", "jikan", "tmdb"],
    "sto": ["tmdb", "tvmaze"],
    "megakinotax": ["tmdb"],
}

# The "kind" hint passed to providers per stream ("tv" vs "movie").
_STREAM_KINDS: dict[str, str] = {
    "aniworldto": "tv",
    "sto": "tv",
    "megakinotax": "movie",
}


def register_provider(name: str, factory) -> None:
    """Register a new metadata provider by name.

    ``factory`` is called without arguments and must return a
    ``MetadataProvider`` instance or raise ``MetadataUnavailableError``.
    """
    _FACTORIES[name] = factory


def chain_for(stream: str) -> list[str]:
    """Return the configured chain of provider names for a stream."""
    try:
        config = json.loads(paths.config_file().read_text()) if paths.config_file().exists() else {}
    except (json.JSONDecodeError, OSError):
        config = {}
    chains = config.get("metadata_chains") or {}
    configured = chains.get(stream)
    if isinstance(configured, list) and configured:
        return [str(n).lower() for n in configured]
    return list(_DEFAULT_CHAINS.get(stream, []))


def kind_for(stream: str) -> str:
    return _STREAM_KINDS.get(stream, "tv")


def build_provider(name: str) -> MetadataProvider | None:
    """Instantiate a provider by name. Returns None if unavailable."""
    factory = _FACTORIES.get(name.lower())
    if factory is None:
        return None
    try:
        return factory()
    except MetadataUnavailableError:
        return None


def available_providers() -> list[str]:
    """Return registered provider names, useful for introspection."""
    return sorted(_FACTORIES.keys())
