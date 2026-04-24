# StreamSeeker — Projekt-Kontext für Claude

StreamSeeker ist eine Python-CLI (ab Python 3.11) zum Herunterladen von Inhalten über
Streaming-Seiten wie **aniworld.to**, **s.to** und **megakino.tax**. Sie verkettet Stream-
Scraper, Provider-Extraktoren (VOE, Filemoon, Vidmoly …) und Downloader (HTTP / ffmpeg)
zu einer einzigen Queue-gesteuerten Pipeline.

## Vertiefende Doku

Für alles, was über diesen Kurz-Einstieg hinausgeht, ist **[docu-intern/](docu-intern/)**
die Quelle der Wahrheit:

- [docu-intern/README.md](docu-intern/README.md) — Einstieg & Navigation
- [docu-intern/architecture.md](docu-intern/architecture.md) — Systemaufbau
- [docu-intern/data-model.md](docu-intern/data-model.md) — Queue/Library/Favorites-Schemas
- [docu-intern/data-location.md](docu-intern/data-location.md) — wo welche Dateien liegen
- [docu-intern/flows.md](docu-intern/flows.md) — Download-, Daemon-, Extension-Flow
- [docu-intern/streams.md](docu-intern/streams.md) — wie Stream-Implementierungen funktionieren
- [docu-intern/conventions.md](docu-intern/conventions.md) — Code-/Pfad-/Naming-Regeln
- [docu-intern/versioning.md](docu-intern/versioning.md) — SemVer & Release-Prozess
- [docu-intern/platform-support.md](docu-intern/platform-support.md) — macOS/Linux/Windows-Scope
- [docu-intern/decisions/](docu-intern/decisions/) — Architecture Decision Records (ADRs)

**Pflege-Regel:** Jede Architekturänderung aktualisiert die passende Doku-Seite. Jede
neue Design-Entscheidung bekommt einen neuen ADR. Wird ein Feature abgeschlossen, wandert
ein Eintrag in [CHANGELOG.md](CHANGELOG.md).

## Einstiegspunkte im Code

| Zweck | Datei |
|---|---|
| CLI-Entry | [src/streamseeker/__main__.py](src/streamseeker/__main__.py) |
| Cleo-Application + Command-Registry | [src/streamseeker/console/application.py](src/streamseeker/console/application.py) |
| Public API für Downloads / Suche | [src/streamseeker/api/handler.py](src/streamseeker/api/handler.py) |
| Queue-Persistenz (thread-safe Singleton) | [src/streamseeker/api/core/downloader/manager.py](src/streamseeker/api/core/downloader/manager.py) |
| Queue-Processor (Background-Worker) | [src/streamseeker/api/core/downloader/processor.py](src/streamseeker/api/core/downloader/processor.py) |
| Zentrale Pfad-API (`~/.streamseeker/`) | [src/streamseeker/paths.py](src/streamseeker/paths.py) |
| Stream-Basisklasse + Implementierungen | [src/streamseeker/api/streams/](src/streamseeker/api/streams/) |
| Provider-Registry + Extraktoren | [src/streamseeker/api/providers/](src/streamseeker/api/providers/) |

## Daten-Layout (harte Regel)

**Alle Runtime-Daten liegen unter `~/.streamseeker/`** — nichts mehr im Projekt-Ordner.
Zugriff ausschließlich über `streamseeker.paths`-API; ENV-Variable `STREAMSEEKER_HOME`
überschreibt den Default. Details in
[docu-intern/data-location.md](docu-intern/data-location.md).

Was im Projekt-Ordner bleibt: Source-Code, Tests, Doku, `pyproject.toml`, `Makefile`.

## Sprache & Konventionen (Kurzfassung)

- Code, Kommentare, Commit-Messages: **Englisch**
- User-Output der CLI, `docu-intern/`-Inhalte: **Deutsch**
- Datei-/Ordner-Namen: **Englisch**
- **Icons sind immer SVG** (ADR 0005). Cover-Artwork ist keine Icon-Nutzung und darf JPG/PNG sein.

## Tests

```bash
pytest tests/
```

Die Tests nutzen `STREAMSEEKER_HOME=<tmp>`-Monkeypatching — kein Test schreibt jemals in
das echte Home-Verzeichnis.

## Versionierung

- **CLI/Backend**: SemVer, Quelle ist `pyproject.toml`. Changelog: [CHANGELOG.md](CHANGELOG.md).
- **Browser-Extension**: SemVer, Quelle ist `extension/manifest.json`. Eigener Changelog
  unter `extension/CHANGELOG.md`. Extension und CLI sind unabhängig releasable (ADR 0006).

## Aktueller Entwicklungsstand (Meta)

Die größere Feature-Welle (Favoriten, Library, FastAPI-Daemon, Chrome-Extension, externe
Metadaten, Distribution) wird in **neun Paketen 0, A, B, C, D, E, F, G, H** gebaut —
siehe [docu-intern/README.md](docu-intern/README.md) für den aktuellen Stand und
`~/.claude/plans/jolly-foraging-puddle.md` für den genehmigten Gesamtplan.
