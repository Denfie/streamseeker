# Architektur

## Ebenenmodell

StreamSeeker besteht aus vier klar getrennten Schichten:

```
┌──────────────────────────────────────────────────────────────┐
│  Frontend                                                    │
│  • CLI (Cleo Commands: run, download, retry, migrate, …)     │
│  • Chrome-Extension (ab Paket F)                             │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│  Orchestration                                               │
│  • StreamseekerHandler  (api/handler.py)                     │
│  • FastAPI-Daemon       (ab Paket D, optional)               │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│  Core                                                        │
│  • DownloadManager      (thread-safe Queue-Persistenz)       │
│  • QueueProcessor       (Background-Worker)                  │
│  • LibraryStore         (ab Paket A)                         │
│  • MetadataResolver     (ab Paket G)                         │
│  • Downloader: standard.py (HTTP), ffmpeg.py (HLS/DASH)      │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│  Adapter / Plugins                                           │
│  • Streams:    aniworldto, sto, megakinotax                  │
│  • Providers:  voe, filemoon, vidmoly, …                     │
└──────────────────────────────────────────────────────────────┘
```

## Schlüsselklassen

### StreamseekerHandler ([api/handler.py](../src/streamseeker/api/handler.py))
Die öffentliche API. Delegiert an Streams und Provider und verwaltet die Config.
Ruft `DownloadManager.enqueue()` (bei Queue-Mode) oder direkt den Downloader
(bei Sofort-Download) auf.

### DownloadManager ([api/core/downloader/manager.py](../src/streamseeker/api/core/downloader/manager.py))
Singleton mit `threading.Lock`. Verwaltet:
- Persistente Queue in `~/.streamseeker/logs/download_queue.json`
- Aktive `tqdm`-Progressbars (`_active_bars`)
- Retry-Contexts
- Thread-Registry für laufende Downloads

### QueueProcessor ([api/core/downloader/processor.py](../src/streamseeker/api/core/downloader/processor.py))
Läuft heute als Daemon-Thread innerhalb des CLI-Prozesses. Zieht pending-Items
aus der Queue und startet pro Item einen Download. Ab Paket D wandert der Worker
in einen separaten Daemon-Prozess.

### Stream-Base ([api/streams/stream_base.py](../src/streamseeker/api/streams/stream_base.py))
Abstrakte Klasse, die jede Stream-Implementierung (aniworldto, sto, megakinotax)
erfüllt: `search`, `search_seasons`, `search_episodes`, `search_providers`,
`search_details`, `download`, `build_file_path`.

### ProviderBase ([api/providers/provider_base.py](../src/streamseeker/api/providers/provider_base.py))
Abstraktion für Video-Hoster. Jeder Provider kennt seinen Namen und liefert aus
einer Hoster-URL eine direkte Download-URL.

## Threading-Modell

- **CLI-Prozess (heute)**: Haupt-Thread rendert die View, `QueueProcessor` läuft
  als Daemon-Thread, pro aktivem Download ein weiterer Worker-Thread.
- **Daemon-Prozess (ab Paket D)**: `QueueProcessor` läuft im Daemon, CLI spricht
  per HTTP. Nur der Daemon schreibt die Queue → keine Inter-Prozess-Race.

## Abhängigkeiten

Aktuell installiert (`pyproject.toml`):
- `cleo` (CLI-Framework), `tqdm` (Progressbars)
- `requests`, `beautifulsoup4`, `selenium` (Scraping)
- Download: intern über `requests` / `ffmpeg` (CLI-Tool, extern bereitgestellt)

Neue Deps (mit Einführung der jeweiligen Pakete):
- `fastapi`, `uvicorn` (Paket D)
- `Pillow` (Paket G für Bild-Re-Encoding)
- Test-seitig: `responses` für HTTP-Mocks (Paket G)
