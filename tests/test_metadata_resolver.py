"""MetadataResolver: provider-chain dispatch + image caching.

Paket G.5 originally exercised a single provider per stream; after ADR 0015
every stream has an ordered *chain* (config-driven). These tests pin
``metadata_chains`` in ``config.json`` so a single provider is exercised in
isolation even when the default chain would try more than one.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from streamseeker import paths
from streamseeker.api.core.helpers import Singleton
from streamseeker.api.core.library import LibraryStore
from streamseeker.api.core.library.store import KIND_LIBRARY
from streamseeker.api.core.metadata.anilist import AniListProvider
from streamseeker.api.core.metadata.base import MetadataMatch
from streamseeker.api.core.metadata.registry import (
    available_providers,
    build_provider,
    chain_for,
    register_provider,
)
from streamseeker.api.core.metadata.resolver import MetadataResolver
from streamseeker.api.core.metadata.tmdb import TmdbProvider


def _write_config(**chains: list[str]) -> None:
    cfg = {"metadata_chains": dict(chains)} if chains else {}
    paths.config_file().write_text(json.dumps(cfg))


@pytest.fixture(autouse=True)
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STREAMSEEKER_HOME", str(tmp_path))
    Singleton._instances.pop(LibraryStore, None)
    paths.credentials_file().write_text(json.dumps({"tmdb_api_key": "testkey"}))
    # Default: each test gets a single-provider chain so existing
    # single-provider tests stay simple. Tests that care about chains
    # override _write_config themselves.
    _write_config(
        aniworldto=["anilist"],
        sto=["tmdb"],
    )
    yield
    Singleton._instances.pop(LibraryStore, None)


def _tiny_png_bytes() -> bytes:
    img = Image.new("RGB", (8, 8), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _match(provider: str, **kwargs) -> MetadataMatch:
    base = dict(
        provider=provider, id=1, title="Dummy",
        overview="desc", year=2020, genres=("Drama",), rating=8.0,
        poster_url="https://cdn/poster.png",
        backdrop_url="https://cdn/backdrop.png",
    )
    base.update(kwargs)
    return MetadataMatch(**base)


# --- registry --------------------------------------------------------


def test_default_chains_match_adr_expectations() -> None:
    # Unset the sandbox override → fall back to registry defaults
    paths.config_file().unlink()
    assert chain_for("aniworldto") == ["anilist", "jikan", "tmdb"]
    assert chain_for("sto") == ["tmdb", "tvmaze"]
    assert chain_for("unknown") == []


def test_chain_respects_config_override() -> None:
    _write_config(sto=["tmdb", "anilist"])
    assert chain_for("sto") == ["tmdb", "anilist"]


def test_build_provider_returns_none_when_unavailable() -> None:
    paths.credentials_file().unlink()
    assert build_provider("tmdb") is None
    # AniList needs no credential and should still come up
    assert isinstance(build_provider("anilist"), AniListProvider)


def test_register_provider_exposes_new_name() -> None:
    class Dummy:
        name = "dummy"

        def search(self, *_a, **_k):
            return None

    register_provider("dummy", Dummy)
    assert "dummy" in available_providers()
    assert isinstance(build_provider("dummy"), Dummy)


# --- enrich ---------------------------------------------------------


def _mock_image_response(body: bytes):
    def fake_get(url, timeout=None, stream=False, **_kw):
        mock = MagicMock()
        mock.status_code = 200
        mock.content = body
        mock.raise_for_status = MagicMock()
        return mock
    return fake_get


def test_enrich_returns_false_for_missing_entry() -> None:
    assert MetadataResolver().enrich("sto::ghost") is False


def test_enrich_no_chain_returns_false() -> None:
    LibraryStore().add(KIND_LIBRARY, {"stream": "unknown", "slug": "x"})
    assert MetadataResolver().enrich("unknown::x") is False


def test_enrich_writes_external_block_and_downloads_images() -> None:
    LibraryStore().add(KIND_LIBRARY, {
        "stream": "aniworldto", "slug": "oshi-no-ko",
        "title": "Oshi No Ko", "year": 2023,
    })

    match = _match("anilist", id=101, title="Oshi No Ko", year=2023,
                   poster_url="https://cdn/poster.png",
                   backdrop_url="https://cdn/banner.png")

    png = _tiny_png_bytes()
    with patch.object(AniListProvider, "search", return_value=match), \
         patch("streamseeker.api.core.metadata.resolver.requests.get",
               side_effect=_mock_image_response(png)):
        assert MetadataResolver().enrich("aniworldto::oshi-no-ko") is True

    entry = LibraryStore().get(KIND_LIBRARY, "aniworldto::oshi-no-ko")
    external = entry["external"]["anilist"]
    assert external["id"] == 101
    assert external["poster"] == "poster.jpg"
    assert external["backdrop"] == "backdrop.jpg"
    assert "fetched_at" in external

    asset_dir = paths.series_dir(KIND_LIBRARY, "aniworldto", "oshi-no-ko")
    assert (asset_dir / "poster.jpg").is_file()
    assert (asset_dir / "backdrop.jpg").is_file()
    data = (asset_dir / "poster.jpg").read_bytes()
    assert data[:3] == b"\xff\xd8\xff"


def test_enrich_survives_image_download_failure() -> None:
    LibraryStore().add(KIND_LIBRARY, {"stream": "aniworldto", "slug": "x", "title": "X"})

    match = _match("anilist", id=1, title="X",
                   poster_url="https://cdn/404.png", backdrop_url=None)

    def fail_get(url, timeout=None, stream=False, **_kw):
        import requests
        raise requests.ConnectionError("boom")

    with patch.object(AniListProvider, "search", return_value=match), \
         patch("streamseeker.api.core.metadata.resolver.requests.get",
               side_effect=fail_get):
        assert MetadataResolver().enrich("aniworldto::x") is True

    entry = LibraryStore().get(KIND_LIBRARY, "aniworldto::x")
    external = entry["external"]["anilist"]
    assert "poster" not in external
    assert external["id"] == 1


def test_enrich_survives_provider_network_error() -> None:
    LibraryStore().add(KIND_LIBRARY, {"stream": "aniworldto", "slug": "x", "title": "X"})

    import requests as _r
    with patch.object(AniListProvider, "search",
                      side_effect=_r.ConnectionError("down")):
        assert MetadataResolver().enrich("aniworldto::x") is False

    entry = LibraryStore().get(KIND_LIBRARY, "aniworldto::x")
    assert entry.get("external", {}) == {}


def test_enrich_fills_missing_year_from_match() -> None:
    LibraryStore().add(KIND_LIBRARY, {"stream": "aniworldto", "slug": "x",
                                      "title": "X", "year": None})
    match = _match("anilist", id=1, title="X", year=2020,
                   poster_url=None, backdrop_url=None)
    with patch.object(AniListProvider, "search", return_value=match):
        MetadataResolver().enrich("aniworldto::x")
    entry = LibraryStore().get(KIND_LIBRARY, "aniworldto::x")
    assert entry["year"] == 2020


def test_enrich_preserves_existing_downloaded_progress() -> None:
    store = LibraryStore()
    store.mark_episode_downloaded("aniworldto::x", 1, 1)
    store.mark_episode_downloaded("aniworldto::x", 1, 2)

    match = _match("anilist", id=1, title="X", poster_url=None, backdrop_url=None)
    with patch.object(AniListProvider, "search", return_value=match):
        MetadataResolver().enrich("aniworldto::x")

    entry = store.get(KIND_LIBRARY, "aniworldto::x")
    assert entry["seasons"]["1"]["downloaded"] == [1, 2]
    assert "anilist" in entry["external"]


def test_enrich_runs_full_chain_and_merges_all_hits() -> None:
    """With a multi-provider chain, every hit contributes its own
    ``external.<provider>`` block. The first hit owns the artwork."""
    _write_config(aniworldto=["anilist", "tmdb"])
    LibraryStore().add(KIND_LIBRARY, {"stream": "aniworldto", "slug": "x", "title": "X"})

    ani_match = _match("anilist", id=1, title="X",
                       poster_url="https://cdn/p.png", backdrop_url=None)
    tmdb_match = _match("tmdb", id=77, title="X",
                        poster_url="https://cdn/p2.png", backdrop_url=None,
                        fsk="FSK 12")

    png = _tiny_png_bytes()
    with patch.object(AniListProvider, "search", return_value=ani_match), \
         patch.object(TmdbProvider, "search", return_value=tmdb_match), \
         patch("streamseeker.api.core.metadata.resolver.requests.get",
               side_effect=_mock_image_response(png)):
        assert MetadataResolver().enrich("aniworldto::x") is True

    entry = LibraryStore().get(KIND_LIBRARY, "aniworldto::x")
    external = entry["external"]
    assert "anilist" in external and "tmdb" in external
    # First provider (anilist) downloaded artwork; second didn't overwrite.
    assert external["anilist"].get("poster") == "poster.jpg"
    assert "poster" not in external["tmdb"]
    # FSK comes from TMDb and must not be lost in the merge
    assert external["tmdb"]["fsk"] == "FSK 12"
