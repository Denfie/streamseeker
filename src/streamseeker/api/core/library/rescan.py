"""Reconstruct Library entries from ``success.log`` for legacy downloads.

For users who downloaded content with pre-Library versions of StreamSeeker
(before the auto-population hook landed), the Library shows nothing. This
module scans the historical ``success.log`` entries and rebuilds Library
records from them.

Line format (see ``DownloadHelper.download_success``)::

    [2026-04-23T12:00:00+00:00] /path/to/file.mp4 :: size=12345

Path conventions we derive stream/slug/season/episode from (mirrors
``build_file_path`` in each stream)::

    downloads/anime/<slug>/Season <N>/<slug>-s<N>e<M>-<lang>.mp4   (aniworldto staffel)
    downloads/anime/<slug>/movies/<slug>-movie-<N>-<lang>.mp4       (aniworldto filme)
    downloads/serie/<slug>/Season <N>/<slug>-s<N>e<M>-<lang>.mp4   (sto staffel)
    downloads/serie/<slug>/movies/<slug>-movie-<N>-<lang>.mp4       (sto filme)
    downloads/movies/megakinotax/<slug>-<lang>.mp4                  (megakinotax)

Everything that doesn't match is reported as ``skipped`` so the user can
inspect them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from streamseeker import paths
from streamseeker.api.core.library.store import KIND_LIBRARY, LibraryStore


# ---------- Path classifiers ----------------------------------------


_STAFFEL_FILE_RE = re.compile(r"(?P<slug>[^/]+?)-s(?P<season>\d+)e(?P<episode>\d+)-")
_MOVIE_FILE_RE = re.compile(r"(?P<slug>[^/]+?)-movie-(?P<num>\d+)-")


@dataclass
class RescanItem:
    """One parsed log entry ready to be upserted into the Library."""
    stream: str
    slug: str
    type: str            # "staffel" or "filme"
    season: int = 0
    episode: int = 0


@dataclass
class RescanReport:
    items: list[RescanItem] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)   # raw paths we couldn't parse


def classify_path(path: str) -> RescanItem | None:
    """Return a RescanItem for ``path`` or None if it can't be classified."""
    parts = path.replace("\\", "/").split("/")
    if "anime" in parts:
        i = parts.index("anime")
        return _classify_series(parts, i, stream="aniworldto")
    if "serie" in parts:
        i = parts.index("serie")
        return _classify_series(parts, i, stream="sto")
    if "movies" in parts and "megakinotax" in parts:
        return _classify_megakinotax(parts)
    return None


def _classify_series(parts: list[str], stream_idx: int, *, stream: str) -> RescanItem | None:
    """Parse downloads/<stream_folder>/<slug>/Season N/<slug>-sXeY-<lang>.mp4
    or downloads/<stream_folder>/<slug>/movies/<slug>-movie-N-<lang>.mp4."""
    try:
        slug = parts[stream_idx + 1]
    except IndexError:
        return None

    filename = parts[-1]

    m = _STAFFEL_FILE_RE.search(filename)
    if m:
        return RescanItem(
            stream=stream, slug=slug, type="staffel",
            season=int(m.group("season")),
            episode=int(m.group("episode")),
        )

    m = _MOVIE_FILE_RE.search(filename)
    if m:
        return RescanItem(
            stream=stream, slug=slug, type="filme",
            episode=int(m.group("num")),
        )

    return None


def _classify_megakinotax(parts: list[str]) -> RescanItem | None:
    """downloads/movies/megakinotax/<slug>-<lang>.mp4 — slug is what stays after
    stripping a trailing -<language>.mp4."""
    filename = parts[-1]
    base = filename.rsplit(".", 1)[0]          # strip .mp4
    slug = base.rsplit("-", 1)[0] or base       # strip -<lang>
    if not slug:
        return None
    return RescanItem(
        stream="megakinotax", slug=slug, type="filme",
        episode=1,
    )


# ---------- The rescan driver ---------------------------------------


def rescan_success_log(log_path: Path | None = None) -> RescanReport:
    """Parse the success log and upsert each classifiable entry into the Library.

    Returns a RescanReport with the parsed items and any lines we couldn't
    classify (so the caller can show them to the user).
    """
    if log_path is None:
        log_path = paths.logs_dir() / "success.log"

    report = RescanReport()
    if not log_path.is_file():
        return report

    store = LibraryStore()

    for raw in log_path.read_text().splitlines():
        if not raw.strip():
            continue
        file_path = _extract_path(raw)
        if not file_path:
            continue

        item = classify_path(file_path)
        if item is None:
            report.skipped.append(file_path)
            continue

        report.items.append(item)
        key = f"{item.stream}::{item.slug}"
        if item.type == "filme":
            store.mark_movie_downloaded(key, item.episode or 1)
        elif item.season > 0 and item.episode > 0:
            store.mark_episode_downloaded(key, item.season, item.episode)
        else:
            report.skipped.append(file_path)

    return report


def _extract_path(line: str) -> str | None:
    """Pull the file path out of a log line like::

        [timestamp] <path> :: size=123
    """
    # Find the first ']' then drop the leading '[timestamp] ' part.
    close = line.find("]")
    if close == -1:
        return None
    rest = line[close + 1:].strip()
    # '<path> :: size=<n>' — split on ' :: ' so paths with spaces stay intact.
    path = rest.split(" :: ", 1)[0].strip()
    return path or None
