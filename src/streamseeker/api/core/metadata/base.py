"""Interface shared by TMDb, AniList and any future metadata provider.

Each provider normalizes its upstream data into a ``MetadataMatch`` so the
``MetadataResolver`` can merge them uniformly into a library entry's
``external.<provider_name>`` block.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterable


class MetadataUnavailableError(RuntimeError):
    """Raised when a provider is known-unavailable (missing API key, disabled).

    Resolver catches this and silently skips the provider.
    """


@dataclass(frozen=True)
class MetadataMatch:
    """A normalized metadata record from one provider.

    ``poster_url`` / ``backdrop_url`` / ``logo_url`` point at remote images;
    downloading them to the local cache is the resolver's job.
    """

    provider: str                       # e.g. "tmdb", "anilist"
    id: int | str
    title: str
    overview: str | None = None
    year: int | None = None
    genres: tuple[str, ...] = ()
    rating: float | None = None
    fsk: str | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    logo_url: str | None = None
    source_url: str | None = None       # canonical URL on the provider's site
    extra: dict = field(default_factory=dict)

    def to_external_block(self, *, poster_file: str | None = None,
                          backdrop_file: str | None = None,
                          logo_file: str | None = None,
                          fetched_at: str | None = None) -> dict:
        """Render the dict shape stored under ``external.<provider>``."""
        block: dict = {"id": self.id, "title": self.title}
        if self.overview is not None:
            block["overview"] = self.overview
        if self.year is not None:
            block["year"] = self.year
        if self.genres:
            block["genres"] = list(self.genres)
        if self.rating is not None:
            block["rating"] = self.rating
        if self.fsk is not None:
            block["fsk"] = self.fsk
        if self.source_url is not None:
            block["source_url"] = self.source_url
        if poster_file is not None:
            block["poster"] = poster_file
        if backdrop_file is not None:
            block["backdrop"] = backdrop_file
        if logo_file is not None:
            block["logo"] = logo_file
        if fetched_at is not None:
            block["fetched_at"] = fetched_at
        if self.extra:
            block["extra"] = dict(self.extra)
        return block


class MetadataProvider(ABC):
    """Shared contract for TMDb/AniList/TVDB clients."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier used in the ``external`` JSON block."""

    @abstractmethod
    def search(self, title: str, *, year: int | None = None,
               kind: str = "tv") -> MetadataMatch | None:
        """Return the best match for ``title`` (None if nothing found).

        ``kind`` is one of ``"tv"`` or ``"movie"`` — providers that don't
        distinguish may ignore it.
        """

    # Providers don't need to override these if ``search`` already returns
    # full detail. TMDb will override ``details`` for a richer lookup.
    def details(self, match_id: int | str) -> MetadataMatch | None:
        return None


def pick_best(matches: Iterable[MetadataMatch], query: str,
              year: int | None = None) -> MetadataMatch | None:
    """Score-based pick used by providers when an API returns many results.

    Exact (case-insensitive) title match wins; otherwise the shortest title
    containing the query wins; a matching year wins ties.
    """
    query_norm = query.lower().strip()
    best: MetadataMatch | None = None
    best_score = -1.0
    for m in matches:
        title_norm = (m.title or "").lower().strip()
        score = 0.0
        if title_norm == query_norm:
            score += 10
        elif query_norm in title_norm:
            score += 5
            # prefer shorter titles — less "extra" padding around the match
            score -= len(title_norm) * 0.01
        if year is not None and m.year == year:
            score += 2
        if score > best_score:
            best_score = score
            best = m
    return best if best_score > 0 else None
