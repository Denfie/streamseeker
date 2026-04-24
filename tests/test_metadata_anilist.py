"""Paket G.4 — AniList GraphQL metadata client."""

from __future__ import annotations

import pytest
import responses

from streamseeker.api.core.metadata.anilist import API_URL, AniListProvider


def _body(media: list[dict]) -> dict:
    return {"data": {"Page": {"media": media}}}


def _media(*, id: int = 1, english: str | None = None, romaji: str = "Oshi no Ko",
           native: str | None = None, year: int | None = 2023,
           score: int | None = 86, description: str | None = "Inhalt …",
           cover: str | None = "https://cdn/poster.jpg",
           banner: str | None = "https://cdn/banner.jpg",
           genres: list[str] | None = None, episodes: int | None = 11,
           format_: str | None = "TV") -> dict:
    return {
        "id": id,
        "title": {"english": english, "romaji": romaji, "native": native},
        "description": description,
        "startDate": {"year": year},
        "averageScore": score,
        "genres": genres or ["Drama"],
        "coverImage": {"extraLarge": cover, "large": cover},
        "bannerImage": banner,
        "studios": {"nodes": [{"name": "Studio X"}]},
        "episodes": episodes,
        "format": format_,
    }


@responses.activate
def test_search_returns_best_match_with_normalized_rating() -> None:
    responses.add(responses.POST, API_URL, json=_body([
        _media(id=101, romaji="Oshi no Ko", year=2023, score=86),
    ]))
    match = AniListProvider().search("Oshi no Ko", year=2023)
    assert match is not None
    assert match.id == 101
    assert match.rating == 8.6  # score 86/10 → 8.6
    assert match.poster_url.endswith("/poster.jpg")
    assert "Drama" in match.genres
    assert match.extra["studios"] == ["Studio X"]


@responses.activate
def test_search_prefers_english_title_when_present() -> None:
    responses.add(responses.POST, API_URL, json=_body([
        _media(id=1, english="My Hero Academia", romaji="Boku no Hero Academia"),
    ]))
    match = AniListProvider().search("My Hero Academia")
    assert match.title == "My Hero Academia"


@responses.activate
def test_search_retries_without_year_when_strict_filter_empty() -> None:
    """First call with year → empty; fallback call without year → match."""
    # First: empty results
    responses.add(responses.POST, API_URL, json=_body([]))
    # Second: the actual match
    responses.add(responses.POST, API_URL, json=_body([_media(id=42, year=2023)]))

    match = AniListProvider().search("Oshi no Ko", year=2024)  # wrong year
    assert match is not None
    assert match.id == 42


@responses.activate
def test_search_returns_none_when_both_queries_empty() -> None:
    responses.add(responses.POST, API_URL, json=_body([]))
    responses.add(responses.POST, API_URL, json=_body([]))
    assert AniListProvider().search("definitely-not-an-anime") is None


@responses.activate
def test_description_html_is_stripped() -> None:
    responses.add(responses.POST, API_URL, json=_body([
        _media(description="Ein <b>Anime</b><br>mit Pathos.<i>Wirklich</i>"),
    ]))
    match = AniListProvider().search("Test")
    assert "<" not in match.overview
    assert "Anime" in match.overview


@responses.activate
def test_missing_score_keeps_rating_none() -> None:
    responses.add(responses.POST, API_URL, json=_body([
        _media(score=None),
    ]))
    match = AniListProvider().search("Test")
    assert match.rating is None


@responses.activate
def test_missing_title_entry_is_skipped() -> None:
    """If AniList returns an entry with no title fields at all, it's dropped."""
    entry = _media(romaji=None, english=None, native=None)
    responses.add(responses.POST, API_URL, json=_body([entry]))
    # Second call (retry without year) returns the same shape
    responses.add(responses.POST, API_URL, json=_body([entry]))
    assert AniListProvider().search("Test") is None
