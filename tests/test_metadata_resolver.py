"""Paket G.5 — MetadataResolver: provider dispatch + image caching."""

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
from streamseeker.api.core.metadata.base import MetadataMatch, MetadataUnavailableError
from streamseeker.api.core.metadata.resolver import MetadataResolver
from streamseeker.api.core.metadata.tmdb import TmdbProvider


@pytest.fixture(autouse=True)
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STREAMSEEKER_HOME", str(tmp_path))
    Singleton._instances.pop(LibraryStore, None)
    # Give TMDb a fake key by default so provider construction succeeds
    paths.credentials_file().write_text(json.dumps({"tmdb_api_key": "testkey"}))
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


# --- provider dispatch ----------------------------------------------


def test_provider_for_aniworldto_is_anilist() -> None:
    resolver = MetadataResolver()
    provider, kind = resolver.provider_for("aniworldto")
    assert isinstance(provider, AniListProvider)
    assert kind == "tv"


def test_provider_for_sto_is_tmdb_tv() -> None:
    resolver = MetadataResolver()
    provider, kind = resolver.provider_for("sto")
    assert isinstance(provider, TmdbProvider)
    assert kind == "tv"


def test_provider_for_megakinotax_is_tmdb_movie() -> None:
    resolver = MetadataResolver()
    provider, kind = resolver.provider_for("megakinotax")
    assert isinstance(provider, TmdbProvider)
    assert kind == "movie"


def test_provider_for_unknown_stream_is_none() -> None:
    resolver = MetadataResolver()
    provider, _ = resolver.provider_for("unknown-stream")
    assert provider is None


def test_provider_for_sto_is_none_without_tmdb_key() -> None:
    paths.credentials_file().unlink()  # remove testkey
    resolver = MetadataResolver()
    provider, _ = resolver.provider_for("sto")
    assert provider is None


def test_provider_for_aniworldto_works_without_tmdb_key() -> None:
    paths.credentials_file().unlink()
    resolver = MetadataResolver()
    provider, _ = resolver.provider_for("aniworldto")
    assert isinstance(provider, AniListProvider)


# --- enrich ---------------------------------------------------------


def _mock_image_response(url: str, body: bytes):
    """Build a MagicMock matching requests.get for an image download."""
    def fake_get(u, timeout=None, stream=False):
        mock = MagicMock()
        mock.status_code = 200
        mock.content = body
        mock.raise_for_status = MagicMock()
        return mock
    return fake_get


def test_enrich_returns_false_for_missing_entry() -> None:
    assert MetadataResolver().enrich("sto::ghost") is False


def test_enrich_no_provider_returns_false() -> None:
    LibraryStore().add(KIND_LIBRARY, {"stream": "unknown", "slug": "x"})
    assert MetadataResolver().enrich("unknown::x") is False


def test_enrich_writes_external_block_and_downloads_images() -> None:
    LibraryStore().add(KIND_LIBRARY, {"stream": "aniworldto", "slug": "oshi-no-ko",
                                      "title": "Oshi No Ko", "year": 2023})

    match = _match("anilist", id=101, title="Oshi No Ko", year=2023,
                   poster_url="https://cdn/poster.png",
                   backdrop_url="https://cdn/banner.png")

    png = _tiny_png_bytes()
    with patch.object(AniListProvider, "search", return_value=match), \
         patch("streamseeker.api.core.metadata.resolver.requests.get",
               side_effect=_mock_image_response("", png)):
        assert MetadataResolver().enrich("aniworldto::oshi-no-ko") is True

    entry = LibraryStore().get(KIND_LIBRARY, "aniworldto::oshi-no-ko")
    external = entry["external"]["anilist"]
    assert external["id"] == 101
    assert external["poster"] == "poster.jpg"
    assert external["backdrop"] == "backdrop.jpg"
    assert "fetched_at" in external

    # Assets on disk
    asset_dir = paths.series_dir(KIND_LIBRARY, "aniworldto", "oshi-no-ko")
    assert (asset_dir / "poster.jpg").is_file()
    assert (asset_dir / "backdrop.jpg").is_file()
    # Re-encoded to JPEG — header check
    data = (asset_dir / "poster.jpg").read_bytes()
    assert data[:3] == b"\xff\xd8\xff"  # JPEG SOI marker


def test_enrich_survives_image_download_failure() -> None:
    """If the image host fails, the external block is still written (no poster)."""
    LibraryStore().add(KIND_LIBRARY, {"stream": "aniworldto", "slug": "x", "title": "X"})

    match = _match("anilist", id=1, title="X",
                   poster_url="https://cdn/404.png", backdrop_url=None)

    def fail_get(u, timeout=None, stream=False):
        import requests
        raise requests.ConnectionError("boom")

    with patch.object(AniListProvider, "search", return_value=match), \
         patch("streamseeker.api.core.metadata.resolver.requests.get",
               side_effect=fail_get):
        assert MetadataResolver().enrich("aniworldto::x") is True

    entry = LibraryStore().get(KIND_LIBRARY, "aniworldto::x")
    external = entry["external"]["anilist"]
    assert "poster" not in external  # download failed, skipped
    assert external["id"] == 1


def test_enrich_survives_provider_network_error() -> None:
    """RequestException from the provider → no external block, no raise."""
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
    """Re-enriching a series with downloaded episodes must not wipe them."""
    store = LibraryStore()
    store.mark_episode_downloaded("aniworldto::x", 1, 1)
    store.mark_episode_downloaded("aniworldto::x", 1, 2)

    match = _match("anilist", id=1, title="X", poster_url=None, backdrop_url=None)
    with patch.object(AniListProvider, "search", return_value=match):
        MetadataResolver().enrich("aniworldto::x")

    entry = store.get(KIND_LIBRARY, "aniworldto::x")
    assert entry["seasons"]["1"]["downloaded"] == [1, 2]
    assert "anilist" in entry["external"]
