# Datenmodell

## Key-Konvention

Ein Inhalt wird systemweit eindeutig durch den Library-Key identifiziert:

```
"{stream_name}::{slug}"
```

Beispiel: `aniworldto::oshi-no-ko`, `sto::breaking-bad`, `megakinotax::dune-part-two`.

Der Slug entspricht dem URL-Pfad-Segment auf der jeweiligen Stream-Seite
(`show.get("link")` im Stream-Code). Er bleibt stabil und eignet sich damit als
primärer Key für Queue-Items, Library-Dateien und Favoriten-Dateien.

## Queue-Item — `download_queue.json`

Eine Liste von Queue-Items (FIFO), persistiert unter
`~/.streamseeker/logs/download_queue.json`. Jedes Item:

```json
{
  "file_name": "downloads/anime/oshi-no-ko/Season 3/oshi-no-ko-s3e9-german.mp4",
  "stream_name": "aniworldto",
  "name": "oshi-no-ko",
  "language": "german",
  "preferred_provider": "voe",
  "type": "staffel",
  "season": 3,
  "episode": 9,
  "status": "pending",
  "attempts": 0,
  "skip_reason": null,
  "last_error": null,
  "added_at": "2026-04-23T12:00:00+02:00"
}
```

Status-Werte: `pending`, `downloading`, `failed`, `skipped`, `paused`. Erfolgreich
abgeschlossene Items werden aus der Queue entfernt.

## Library-Eintrag (ab Paket A)

Eine JSON-Datei pro Serie unter `~/.streamseeker/library/<stream>/<slug>.json`.

```json
{
  "key": "aniworldto::oshi-no-ko",
  "stream": "aniworldto",
  "slug": "oshi-no-ko",
  "title": "Oshi No Ko",
  "year": 2023,
  "type": "staffel",
  "url": "https://aniworld.to/anime/stream/oshi-no-ko",
  "added_at": "2026-04-23T12:00:00Z",
  "seasons": {
    "1": { "episode_count": 11, "downloaded": [1, 2, 3] },
    "2": { "episode_count": 13, "downloaded": [] }
  },
  "movies": { "downloaded": [] },
  "notes": null,
  "external": {}
}
```

Das Feld `external` wird in Paket G von externen Metadaten-Quellen befüllt
(siehe unten).

### Assets pro Serie (ab Paket G)
Neben der JSON-Datei liegt ein gleichnamiger Ordner mit Bildern:

```
~/.streamseeker/library/aniworldto/oshi-no-ko.json
~/.streamseeker/library/aniworldto/oshi-no-ko/
  ├── poster.jpg        # vertical, ~500×750
  ├── backdrop.jpg      # landscape, ~1280×720
  ├── logo.png          # optional, transparent
  └── seasons/
      ├── s01-poster.jpg
      ├── s01e01.jpg    # episode thumbnail (optional)
      └── s01e02.jpg
```

Dateinamen sind **fest** (unabhängig von der Quelle), damit Extension und CLI
Pfade ohne Config-Lookup bilden können.

### `external.tmdb` / `external.anilist` (Paket G)

```json
{
  "external": {
    "tmdb": {
      "id": 1396,
      "overview": "Ein Chemielehrer …",
      "poster": "poster.jpg",
      "backdrop": "backdrop.jpg",
      "genres": ["Drama", "Crime"],
      "rating": 8.9,
      "fsk": "FSK 16",
      "fetched_at": "2026-04-23T12:00:00Z"
    }
  }
}
```

Wichtig: im JSON werden **relative Dateinamen** abgelegt, keine URLs — die URLs
werden beim Fetch in lokale Cover-Dateien aufgelöst.

## Favoriten-Eintrag (ab Paket A)

Identisches Schema wie Library, aber in separatem Baum
`~/.streamseeker/favorites/<stream>/<slug>.json`. Beim "Promote to Library"
wandert die Datei unverändert um.

## Index-Datei (`index.json`)

Für schnelle Übersicht/Suche ohne alle Einzel-JSONs zu öffnen. Liegt in
`library/index.json` und `favorites/index.json`:

```json
[
  {
    "key": "aniworldto::oshi-no-ko",
    "title": "Oshi No Ko",
    "stream": "aniworldto",
    "type": "staffel",
    "year": 2023,
    "downloaded_count": 4,
    "total_count": 24
  }
]
```

Wird bei jedem `add`/`remove`/`mark_episode_downloaded` neu geschrieben. Kann
aus den Einzel-Dateien rekonstruiert werden (`LibraryStore._rebuild_index()`).

## Config (`config.json`)

Liegt unter `~/.streamseeker/config.json`. Enthält nur User-Einstellungen,
keine Runtime-Daten.

Default-Werte siehe [handler.py → DEFAULTS](../src/streamseeker/api/handler.py).
Feld-Dokumentation:

| Schlüssel | Typ | Default | Bedeutung |
|---|---|---|---|
| `preferred_provider` | str | `"voe"` | Erster Provider-Kandidat |
| `output_folder` | str | `"downloads"` | Pfad (relativ → `~/.streamseeker/`, absolut → so lassen) |
| `output_folder_year` | bool | `false` | Jahr im Download-Pfad anhängen |
| `overwrite` | bool | `false` | Existierende Dateien überschreiben |
| `max_concurrent` | int | `2` | Parallele Downloads |
| `max_retries` | int | `3` | Auto-Retry pro Item |
| `ddos_limit` | int | `3` | Schwelle, ab der das Tool pausiert |
| `ddos_timer` | int | `90` | Wartezeit (s) nach Auslösen |
| `start_delay_min/max` | int | `5`/`25` | Zufallsverzögerung zwischen Starts |

## Credentials (`config.credentials.json`)

Liegt unter `~/.streamseeker/config.credentials.json`, `chmod 600`. Nie ins Git.

```json
{
  "tmdb_api_key": "xxxxx",
  "tvdb_api_key": null
}
```

AniList braucht keinen Key (Public GraphQL API).
