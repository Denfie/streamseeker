"""Paket G.3 — TMDb metadata client (HTTP mocked with `responses`)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import responses

from streamseeker import paths
from streamseeker.api.core.metadata.base import MetadataUnavailableError
from streamseeker.api.core.metadata.tmdb import API_BASE, TmdbProvider


@pytest.fixture(autouse=True)
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STREAMSEEKER_HOME", str(tmp_path))
    yield


@pytest.fixture
def provider(sandbox: Path) -> TmdbProvider:
    paths.credentials_file().write_text(json.dumps({"tmdb_api_key": "testkey"}))
    return TmdbProvider()


def _mock_configuration(rsps: responses.RequestsMock) -> None:
    rsps.add(
        responses.GET,
        f"{API_BASE}/configuration",
        json={"images": {"secure_base_url": "https://image.tmdb.org/t/p/"}},
    )


# --- API key handling -----------------------------------------------


def test_missing_key_raises_unavailable(sandbox: Path) -> None:
    with pytest.raises(MetadataUnavailableError):
        TmdbProvider()


def test_explicit_key_overrides_config(sandbox: Path) -> None:
    p = TmdbProvider(api_key="inline-key")
    assert p._api_key == "inline-key"


def test_credentials_file_provides_key(sandbox: Path) -> None:
    paths.credentials_file().write_text(json.dumps({"tmdb_api_key": "from-file"}))
    p = TmdbProvider()
    assert p._api_key == "from-file"


# --- search_tv → details merge -------------------------------------


@responses.activate
def test_search_tv_returns_enriched_match(provider: TmdbProvider) -> None:
    _mock_configuration(responses)
    responses.add(
        responses.GET,
        f"{API_BASE}/search/tv",
        json={"results": [
            {
                "id": 1396,
                "name": "Breaking Bad",
                "overview": "Chemielehrer …",
                "first_air_date": "2008-01-20",
                "vote_average": 8.91,
                "poster_path": "/poster.jpg",
                "backdrop_path": "/bd.jpg",
            }
        ]},
    )
    responses.add(
        responses.GET,
        f"{API_BASE}/tv/1396",
        json={
            "id": 1396,
            "name": "Breaking Bad",
            "overview": "Chemielehrer …",
            "first_air_date": "2008-01-20",
            "genres": [{"id": 18, "name": "Drama"}, {"id": 80, "name": "Crime"}],
            "vote_average": 8.9,
            "poster_path": "/poster.jpg",
            "backdrop_path": "/bd.jpg",
            "content_ratings": {"results": [
                {"iso_3166_1": "US", "rating": "TV-MA"},
                {"iso_3166_1": "DE", "rating": "16"},
            ]},
        },
    )

    match = provider.search("Breaking Bad", year=2008, kind="tv")
    assert match is not None
    assert match.id == 1396
    assert match.title == "Breaking Bad"
    assert "Drama" in match.genres
    assert match.fsk == "FSK 16"  # DE wins over US
    assert match.rating == 8.9
    assert match.poster_url == "https://image.tmdb.org/t/p/w500/poster.jpg"
    assert match.backdrop_url == "https://image.tmdb.org/t/p/w1280/bd.jpg"


@responses.activate
def test_search_tv_returns_none_on_empty_results(provider: TmdbProvider) -> None:
    responses.add(
        responses.GET,
        f"{API_BASE}/search/tv",
        json={"results": []},
    )
    assert provider.search("ghost", kind="tv") is None


@responses.activate
def test_search_prefers_exact_title_over_first_result(provider: TmdbProvider) -> None:
    _mock_configuration(responses)
    responses.add(
        responses.GET,
        f"{API_BASE}/search/tv",
        json={"results": [
            {"id": 1, "name": "Breaking Bad: El Camino",
             "first_air_date": "2019-10-11", "poster_path": "/a.jpg",
             "backdrop_path": None, "overview": "", "vote_average": 7.0},
            {"id": 2, "name": "Breaking Bad",
             "first_air_date": "2008-01-20", "poster_path": "/b.jpg",
             "backdrop_path": None, "overview": "", "vote_average": 9.0},
        ]},
    )
    responses.add(
        responses.GET,
        f"{API_BASE}/tv/2",
        json={"id": 2, "name": "Breaking Bad",
              "first_air_date": "2008-01-20", "genres": [],
              "content_ratings": {"results": []}},
    )
    match = provider.search("Breaking Bad", kind="tv")
    assert match.id == 2


# --- search_movie --------------------------------------------------


@responses.activate
def test_search_movie_picks_certification(provider: TmdbProvider) -> None:
    _mock_configuration(responses)
    responses.add(
        responses.GET,
        f"{API_BASE}/search/movie",
        json={"results": [
            {"id": 438631, "title": "Dune: Part Two",
             "release_date": "2024-02-27", "poster_path": "/p.jpg",
             "backdrop_path": "/b.jpg", "overview": "", "vote_average": 8.2},
        ]},
    )
    responses.add(
        responses.GET,
        f"{API_BASE}/movie/438631",
        json={
            "id": 438631, "title": "Dune: Part Two",
            "release_date": "2024-02-27",
            "genres": [{"id": 878, "name": "Science Fiction"}],
            "release_dates": {"results": [
                {"iso_3166_1": "US", "release_dates": [{"certification": "PG-13"}]},
                {"iso_3166_1": "DE", "release_dates": [{"certification": "12"}]},
            ]},
        },
    )
    match = provider.search("Dune: Part Two", kind="movie")
    assert match.fsk == "FSK 12"
    assert "Science Fiction" in match.genres


# --- details 404 ---------------------------------------------------


@responses.activate
def test_details_returns_none_on_404(provider: TmdbProvider) -> None:
    responses.add(
        responses.GET, f"{API_BASE}/tv/999999",
        json={"status_code": 34, "status_message": "not found"},
        status=404,
    )
    assert provider.details(999999, kind="tv") is None


# --- MetadataMatch.to_external_block -------------------------------


def test_to_external_block_contains_only_known_fields() -> None:
    from streamseeker.api.core.metadata.base import MetadataMatch

    m = MetadataMatch(
        provider="tmdb", id=1, title="X",
        overview="…", year=2020, genres=("Drama",),
        rating=8.5, fsk="FSK 16",
        poster_url="https://…/p.jpg", backdrop_url="https://…/b.jpg",
    )
    block = m.to_external_block(
        poster_file="poster.jpg", backdrop_file="backdrop.jpg",
        fetched_at="2026-04-23T00:00:00Z",
    )
    assert block["id"] == 1
    assert block["poster"] == "poster.jpg"
    assert block["backdrop"] == "backdrop.jpg"
    assert block["fsk"] == "FSK 16"
    assert block["fetched_at"] == "2026-04-23T00:00:00Z"
    # remote URLs are not stored
    assert "poster_url" not in block
    assert "backdrop_url" not in block
