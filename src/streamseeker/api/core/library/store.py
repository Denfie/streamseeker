"""Thread-safe file-based storage for the Library and Favorites.

One JSON per series under ``~/.streamseeker/library/<stream>/<slug>.json``
or ``~/.streamseeker/favorites/<stream>/<slug>.json``, plus a compact
``index.json`` per kind for fast listing/search.

All writes are serialized through a single lock and use an atomic
``.tmp → rename`` pattern so a crash mid-write cannot corrupt the index
or an individual entry.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from streamseeker import paths
from streamseeker.api.core.helpers import Singleton


KIND_LIBRARY = "library"
KIND_FAVORITES = "favorites"
_KINDS = (KIND_LIBRARY, KIND_FAVORITES)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    os.replace(tmp, path)


def _parse_key(key: str) -> tuple[str, str]:
    if "::" not in key:
        raise ValueError(f"invalid library key {key!r} — expected '<stream>::<slug>'")
    stream, slug = key.split("::", 1)
    if not stream or not slug:
        raise ValueError(f"invalid library key {key!r} — stream/slug must be non-empty")
    return stream, slug


class LibraryStore(metaclass=Singleton):
    """Single writer for Library and Favorites data on disk."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, kind: str, entry: dict) -> dict:
        """Upsert an entry. Returns the stored entry.

        If the key already exists, fields present in ``entry`` overwrite
        the stored version, but ``seasons[].downloaded`` arrays are merged
        (union, sorted) so progress is never lost by re-adding.
        """
        self._require_kind(kind)
        key = self._require_key(entry)
        with self._lock:
            existing = self._read_entry(kind, key)
            merged = self._merge(existing, entry) if existing else self._with_defaults(entry)
            self._write_entry(kind, merged)
            self._update_index_row(kind, merged)
            return merged

    def remove(self, kind: str, key: str) -> bool:
        """Delete an entry (JSON + asset folder). Returns True if it existed."""
        self._require_kind(kind)
        stream, slug = _parse_key(key)
        with self._lock:
            file = paths.series_file(kind, stream, slug)
            if not file.exists():
                return False
            file.unlink()
            assets = paths.series_dir(kind, stream, slug)
            if assets.exists() and assets.is_dir():
                shutil.rmtree(assets)
            self._remove_index_row(kind, key)
            return True

    def get(self, kind: str, key: str) -> dict | None:
        self._require_kind(kind)
        with self._lock:
            return self._read_entry(kind, key)

    def list(self, kind: str) -> list[dict]:
        """Return all index rows. Fast — reads only ``index.json``."""
        self._require_kind(kind)
        with self._lock:
            return self._read_index(kind)

    def search(self, kind: str, term: str) -> list[dict]:
        """Case-insensitive match against title and slug in the index."""
        self._require_kind(kind)
        needle = term.strip().lower()
        if not needle:
            return []
        with self._lock:
            return [
                row
                for row in self._read_index(kind)
                if needle in row.get("title", "").lower()
                or needle in row.get("slug", "").lower()
            ]

    def mark_episode_downloaded(self, key: str, season: int, episode: int) -> dict:
        """Record a downloaded episode in the Library.

        Always writes to the Library kind. Creates a skeleton entry if the
        key isn't there yet so progress survives even if the upstream
        enrichment (Paket B) skipped the upsert.
        """
        stream, slug = _parse_key(key)
        season_key = str(season)
        with self._lock:
            entry = self._read_entry(KIND_LIBRARY, key) or self._skeleton(stream, slug)
            seasons = entry.setdefault("seasons", {})
            season_data = seasons.setdefault(season_key, {"episode_count": 0, "downloaded": []})
            downloaded = set(season_data.get("downloaded", []))
            downloaded.add(episode)
            season_data["downloaded"] = sorted(downloaded)
            if season_data.get("episode_count", 0) < episode:
                season_data["episode_count"] = episode
            self._write_entry(KIND_LIBRARY, entry)
            self._update_index_row(KIND_LIBRARY, entry)
            return entry

    def mark_movie_downloaded(self, key: str, movie_number: int) -> dict:
        """Record a downloaded movie (type=='filme') in the Library."""
        stream, slug = _parse_key(key)
        with self._lock:
            entry = self._read_entry(KIND_LIBRARY, key) or self._skeleton(stream, slug)
            movies = entry.setdefault("movies", {"downloaded": []})
            downloaded = set(movies.get("downloaded", []))
            downloaded.add(movie_number)
            movies["downloaded"] = sorted(downloaded)
            self._write_entry(KIND_LIBRARY, entry)
            self._update_index_row(KIND_LIBRARY, entry)
            return entry

    # ------------------------------------------------------------------
    # Favorite flag (collection = library + optional `favorite: true` flag)
    # ------------------------------------------------------------------

    def set_favorite(self, key: str, value: bool) -> dict:
        """Toggle the ``favorite`` flag on a library entry.

        Creates a skeleton library entry if the key isn't stored yet, so the
        extension's ⭐-toggle works even on shows the user hasn't downloaded.
        Returns the updated entry.
        """
        stream, slug = _parse_key(key)
        with self._lock:
            entry = self._read_entry(KIND_LIBRARY, key) or self._skeleton(stream, slug)
            entry["favorite"] = bool(value)
            entry.setdefault("added_at", _now())
            self._write_entry(KIND_LIBRARY, entry)
            self._update_index_row(KIND_LIBRARY, entry)
            return entry

    def list_collection(self, *, favorite_only: bool = False) -> list[dict]:
        """Return the merged collection view — all library entries, with
        the ``favorite`` bool mirrored in the index row. ``favorite_only``
        restricts the result to flagged entries."""
        with self._lock:
            rows = self._read_index(KIND_LIBRARY)
        if favorite_only:
            return [r for r in rows if r.get("favorite")]
        return rows

    def move_favorite_to_library(self, key: str) -> dict:
        """Promote a Favorite entry (and its assets) into the Library.

        If a Library entry already exists, the two are merged via ``add``.
        The source Favorite is removed on success.
        """
        stream, slug = _parse_key(key)
        with self._lock:
            src_file = paths.series_file(KIND_FAVORITES, stream, slug)
            if not src_file.exists():
                raise FileNotFoundError(f"no favorite {key!r}")
            entry = json.loads(src_file.read_text())
            existing = self._read_entry(KIND_LIBRARY, key)
            merged = self._merge(existing, entry) if existing else self._with_defaults(entry)
            self._write_entry(KIND_LIBRARY, merged)
            self._update_index_row(KIND_LIBRARY, merged)

            # Move assets folder if present
            src_assets = paths.series_dir(KIND_FAVORITES, stream, slug)
            dst_assets = paths.series_dir(KIND_LIBRARY, stream, slug)
            if src_assets.exists():
                dst_assets.parent.mkdir(parents=True, exist_ok=True)
                if dst_assets.exists():
                    # merge asset dirs — destination wins on name collision
                    for asset in src_assets.rglob("*"):
                        if asset.is_file():
                            rel = asset.relative_to(src_assets)
                            target = dst_assets / rel
                            if not target.exists():
                                target.parent.mkdir(parents=True, exist_ok=True)
                                shutil.move(str(asset), str(target))
                    shutil.rmtree(src_assets)
                else:
                    shutil.move(str(src_assets), str(dst_assets))

            src_file.unlink()
            self._remove_index_row(KIND_FAVORITES, key)
            return merged

    def migrate_favorites_into_library(self) -> int:
        """Merge every legacy `~/.streamseeker/favorites/*` JSON into the
        Library, tagging each merged entry with ``favorite: true``.

        Idempotent: if the favorites folder is empty or gone, returns 0.
        Safe to call on every daemon startup.
        """
        moved = 0
        fav_root = paths.favorites_dir()
        if not fav_root.exists():
            return 0
        for stream_dir in sorted(p for p in fav_root.iterdir() if p.is_dir()):
            for entry_file in sorted(stream_dir.glob("*.json")):
                try:
                    entry = json.loads(entry_file.read_text())
                except (json.JSONDecodeError, OSError):
                    continue
                key = entry.get("key")
                if not key:
                    continue
                stream, slug = _parse_key(key)

                # Merge payload into library with favorite=true
                entry["favorite"] = True
                self.add(KIND_LIBRARY, entry)

                # Move asset files (poster, backdrop, …) into the library
                # series dir unless the library already has the asset.
                src_assets = paths.series_dir(KIND_FAVORITES, stream, slug)
                dst_assets = paths.series_dir(KIND_LIBRARY, stream, slug)
                if src_assets.exists() and src_assets.is_dir():
                    dst_assets.mkdir(parents=True, exist_ok=True)
                    for asset in src_assets.rglob("*"):
                        if asset.is_file():
                            rel = asset.relative_to(src_assets)
                            target = dst_assets / rel
                            if not target.exists():
                                target.parent.mkdir(parents=True, exist_ok=True)
                                shutil.move(str(asset), str(target))
                    shutil.rmtree(src_assets, ignore_errors=True)

                entry_file.unlink()
                moved += 1
            # Prune empty stream folders
            try:
                stream_dir.rmdir()
            except OSError:
                pass

        # Final cleanup: remove the favorites index + empty root
        idx = paths.favorites_index_file()
        if idx.exists():
            idx.unlink()
        try:
            fav_root.rmdir()
        except OSError:
            pass
        return moved

    def rebuild_index(self, kind: str) -> list[dict]:
        """Reconstruct ``index.json`` by scanning the on-disk entries.

        Use when ``index.json`` is missing, corrupt, or out of sync with
        the per-series files. Returns the new index.
        """
        self._require_kind(kind)
        with self._lock:
            return self._rebuild_index(kind)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _require_kind(kind: str) -> None:
        if kind not in _KINDS:
            raise ValueError(f"kind must be one of {_KINDS}, got {kind!r}")

    @staticmethod
    def _require_key(entry: dict) -> str:
        key = entry.get("key")
        if not key:
            stream = entry.get("stream")
            slug = entry.get("slug")
            if not stream or not slug:
                raise ValueError("entry requires 'key' or ('stream' + 'slug')")
            key = f"{stream}::{slug}"
            entry["key"] = key
        _parse_key(key)  # validate shape
        return key

    @staticmethod
    def _skeleton(stream: str, slug: str) -> dict:
        return {
            "key": f"{stream}::{slug}",
            "stream": stream,
            "slug": slug,
            "title": slug.replace("-", " ").replace("_", " ").strip().title() or slug,
            "year": None,
            "type": None,
            "url": None,
            "added_at": _now(),
            "favorite": False,
            "seasons": {},
            "movies": {"downloaded": []},
            "notes": None,
            "external": {},
        }

    @classmethod
    def _with_defaults(cls, entry: dict) -> dict:
        stream, slug = _parse_key(cls._require_key(entry))
        merged = cls._skeleton(stream, slug)
        merged.update({k: v for k, v in entry.items() if v is not None or k == "notes"})
        # preserve caller-provided seasons/movies structure
        merged.setdefault("seasons", entry.get("seasons", {}))
        merged.setdefault("movies", entry.get("movies", {"downloaded": []}))
        merged.setdefault("external", entry.get("external", {}))
        merged.setdefault("added_at", _now())
        return merged

    @staticmethod
    def _merge(existing: dict, incoming: dict) -> dict:
        """Shallow-merge incoming fields into existing, preserving progress.

        Rules:
        - Scalar fields: incoming wins unless it's None/missing.
        - ``seasons``: union per season key; ``downloaded`` arrays merged as set;
          ``episode_count`` takes max(existing, incoming).
        - ``movies.downloaded``: union.
        - ``external``: deep-merge per provider key.
        - ``added_at``: existing wins.
        """
        result = dict(existing)
        for k, v in incoming.items():
            if k in ("seasons", "movies", "external", "added_at"):
                continue
            if v is not None:
                result[k] = v

        # seasons
        merged_seasons = dict(existing.get("seasons", {}))
        for season_key, season_data in incoming.get("seasons", {}).items():
            merged_seasons.setdefault(season_key, {"episode_count": 0, "downloaded": []})
            current = merged_seasons[season_key]
            if "episode_count" in season_data:
                current["episode_count"] = max(
                    current.get("episode_count", 0), season_data["episode_count"]
                )
            if "downloaded" in season_data:
                combined = set(current.get("downloaded", [])) | set(season_data["downloaded"])
                current["downloaded"] = sorted(combined)
        if merged_seasons:
            result["seasons"] = merged_seasons

        # movies
        existing_movies = existing.get("movies", {}) or {}
        incoming_movies = incoming.get("movies", {}) or {}
        movie_downloaded = set(existing_movies.get("downloaded", [])) | set(
            incoming_movies.get("downloaded", [])
        )
        result["movies"] = {"downloaded": sorted(movie_downloaded)}

        # external — deep merge one level (per provider key)
        ext = dict(existing.get("external", {}))
        for provider, data in incoming.get("external", {}).items():
            if isinstance(ext.get(provider), dict) and isinstance(data, dict):
                ext[provider] = {**ext[provider], **data}
            else:
                ext[provider] = data
        result["external"] = ext

        # preserve original added_at
        result["added_at"] = existing.get("added_at", incoming.get("added_at") or _now())
        return result

    @staticmethod
    def _read_entry(kind: str, key: str) -> dict | None:
        stream, slug = _parse_key(key)
        file = paths.series_file(kind, stream, slug)
        if not file.is_file():
            return None
        try:
            return json.loads(file.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def _write_entry(kind: str, entry: dict) -> None:
        key = entry["key"]
        stream, slug = _parse_key(key)
        file = paths.series_file(kind, stream, slug)
        _atomic_write_json(file, entry)

    @staticmethod
    def _index_file(kind: str) -> Path:
        return (
            paths.library_index_file() if kind == KIND_LIBRARY else paths.favorites_index_file()
        )

    @classmethod
    def _read_index(cls, kind: str) -> list[dict]:
        file = cls._index_file(kind)
        if not file.is_file():
            return []
        try:
            data = json.loads(file.read_text())
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    @classmethod
    def _write_index(cls, kind: str, rows: list[dict]) -> None:
        _atomic_write_json(cls._index_file(kind), rows)

    @classmethod
    def _update_index_row(cls, kind: str, entry: dict) -> None:
        rows = cls._read_index(kind)
        row = cls._index_row(entry)
        for i, existing in enumerate(rows):
            if existing.get("key") == row["key"]:
                rows[i] = row
                break
        else:
            rows.append(row)
        cls._write_index(kind, rows)

    @classmethod
    def _remove_index_row(cls, kind: str, key: str) -> None:
        rows = [r for r in cls._read_index(kind) if r.get("key") != key]
        cls._write_index(kind, rows)

    @staticmethod
    def _index_row(entry: dict) -> dict:
        seasons = entry.get("seasons", {}) or {}
        movies = entry.get("movies", {}) or {}
        downloaded = sum(len(s.get("downloaded", [])) for s in seasons.values())
        downloaded += len(movies.get("downloaded", []))
        total = sum(s.get("episode_count", 0) for s in seasons.values())
        return {
            "key": entry["key"],
            "title": entry.get("title"),
            "stream": entry.get("stream"),
            "slug": entry.get("slug"),
            "type": entry.get("type"),
            "year": entry.get("year"),
            "favorite": bool(entry.get("favorite")),
            "has_updates": bool(entry.get("pending_updates")),
            "downloaded_count": downloaded,
            "total_count": total,
        }

    @classmethod
    def _rebuild_index(cls, kind: str) -> list[dict]:
        root = paths.library_dir() if kind == KIND_LIBRARY else paths.favorites_dir()
        rows: list[dict] = []
        if root.is_dir():
            for stream_dir in sorted(p for p in root.iterdir() if p.is_dir()):
                for entry_file in sorted(stream_dir.glob("*.json")):
                    try:
                        entry = json.loads(entry_file.read_text())
                    except (json.JSONDecodeError, OSError):
                        continue
                    if "key" in entry:
                        rows.append(cls._index_row(entry))
        cls._write_index(kind, rows)
        return rows
