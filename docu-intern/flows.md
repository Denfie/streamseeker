# Flows

Zentrale Abläufe als ASCII-Diagramme. Detail-Code ist verlinkt, die Diagramme
bleiben bewusst grob — sie sollen Orientierung geben, nicht 1:1 den Code spiegeln.

## 1. Download-Flow (heute, ohne Daemon)

```
User CLI                          Handler                  DownloadManager        QueueProcessor
────────                          ───────                  ───────────────        ──────────────
│                                   │                             │                     │
├── streamseeker download ────────►│                             │                     │
│                                   ├── stream.search() ──►   (Scraping, Provider-Pick) │
│                                   │                             │                     │
│                                   ├── enqueue_single() ──────► enqueue() ──► JSON     │
│                                   │                             │                     │
├── streamseeker run (View) ───────┐                             │                     │
│                                   │                             ◄── start() ──────────┤ (Daemon-Thread)
│◄─── Live-Progress via tqdm ──────┘                             │                     │ pulls pending,
│                                                                 │                     │ runs downloader,
│                                                                 ◄── mark_status() ────┤ updates JSON
│                                                                 │                     │
│◄─── Gruppierte Queue-Ansicht ◄──────────────────────────────────┤                     │
│     (aktive Bars + "Name (count)")                              │                     │
```

Quelle: [run.py → `_render_view`](../src/streamseeker/console/commands/run.py),
[processor.py](../src/streamseeker/api/core/downloader/processor.py).

## 2. Daemon-Flow (ab Paket D)

```
CLI-Prozess                       FastAPI-Daemon (eigener Prozess)      Browser-Extension
───────────                       ──────────────────────────────────    ─────────────────
│                                   │                                      │
├── streamseeker daemon start ────►│  (uvicorn auf 127.0.0.1:8765)        │
│                                   │  QueueProcessor läuft hier           │
│                                   │  LibraryStore-Lock hier              │
│                                   │                                      │
├── streamseeker download ─────────►│ POST /queue  ──────────►             │
│                                   │                                      │
├── streamseeker run ──────────────►│ GET /events (SSE)   ◄── push ────    │
│◄── Live-Status aus SSE ───────────│                                      │
│                                   │                                      │
│                                   │◄── POST /favorites  ◄────────────────┤
│                                   │◄── GET /library/state ◄──────────────┤
│                                   │◄── GET /events (SSE) ◄───────────────┤
```

**Single-Writer-Prinzip:** Nur der Daemon-Prozess schreibt Queue/Library/Favoriten.
CLI und Extension senden Befehle per HTTP → keine Race-Conditions.

**Daemon-optional:** Ohne laufenden Daemon fällt die CLI auf den direkten
Handler-Pfad (Diagramm 1) zurück. `daemon_client.is_daemon_running()` pingt
`/status` mit 200 ms Timeout und entscheidet anhand der Antwort.

## 3. Extension-Flow (ab Paket F)

```
Serien-Seite im Chrome             Content-Script                 Daemon
──────────────────────             ──────────────                 ──────
│                                   │                               │
├── URL erkannt ──────────────────►│ parse stream + slug            │
│                                   ├── GET /library/state ───────►│
│                                   │                               │ (liest Library + Queue)
│                                   │◄── {favorite, library,       ─┤
│                                   │    seasons: {...}} ──────────│
│                                   │                               │
│  Icons gerendert:                 │                               │
│  ⭐ / ☆   (Favorit)               │                               │
│  ⬇ / ◐ / ☐ (Download-Status)     │                               │
│  + Zähler "3/12" pro Staffel     │                               │
│                                   │                               │
├── Klick auf ☆ ───────────────────►│ POST /favorites ────────────►│
│                                   │◄── 201 ─────────────────────│
│  Icon wechselt zu ⭐             │                               │
│                                   │                               │
│                                   ├── SSE /events abonniert ────►│
│                                   │◄── {type: "progress", ...} ─┤
│  Download-Icons aktualisieren     │                               │
│  sich live, ohne Reload           │                               │
```

Quelle-Details: `extension/content_scripts/*.js`, Daemon-Endpoint
`GET /library/state` in Paket F ergänzt.

## 4. Metadaten-Enrichment (ab Paket G)

```
neue Serie wird zu Library hinzugefügt
        │
        ▼
LibraryStore.upsert(entry)
        │
        ▼  (async, eigener Thread — blockiert keinen Download)
MetadataResolver.enrich(entry)
        │
        ├── Stream == aniworldto? ──► AniListClient.search(title) → details
        ├── Stream == sto?        ──► TmdbClient.search_tv(title) → details
        └── Stream == megakinotax?──► TmdbClient.search_movie(title) → details
        │
        ▼
  external = {...}
  poster_url, backdrop_url → lokal herunterladen (Pillow, ≤85% JPEG)
        │
        ▼
~/.streamseeker/library/<stream>/<slug>/
  ├── poster.jpg
  └── backdrop.jpg
        │
        ▼
Library-JSON aktualisiert:
  "external": {"tmdb": {"id": 1396, "poster": "poster.jpg", ...}}
```

Fehler beim Enrich (Netz weg, 404, kein API-Key) → nur Warn-Log, Library-Eintrag
bleibt valide. Re-Fetch manuell über `streamseeker library refresh <key>`.
