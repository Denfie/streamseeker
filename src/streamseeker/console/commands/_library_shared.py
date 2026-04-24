"""Shared helpers for the ``favorite`` and ``library`` command families."""

from __future__ import annotations


def format_key(stream: str, slug: str) -> str:
    return f"{stream}::{slug}"


def format_row(row: dict) -> str:
    """One-line summary of an index row for list/search output."""
    downloaded = row.get("downloaded_count", 0)
    total = row.get("total_count", 0) or 0
    progress = f"{downloaded}/{total}" if total else f"{downloaded}"
    year = f" ({row['year']})" if row.get("year") else ""
    stream = row.get("stream", "?")
    title = row.get("title") or row.get("slug", "?")
    return f"  {title}{year}  <comment>[{stream}]</comment>  {progress} Ep."


def parse_key_arg(key: str) -> tuple[str, str]:
    """Parse ``<stream>::<slug>`` into its parts, raising ValueError otherwise."""
    if "::" not in key:
        raise ValueError(
            f"invalid key {key!r} — expected format '<stream>::<slug>' (e.g. sto::breaking-bad)"
        )
    stream, slug = key.split("::", 1)
    if not stream or not slug:
        raise ValueError(f"invalid key {key!r} — stream and slug must be non-empty")
    return stream, slug
