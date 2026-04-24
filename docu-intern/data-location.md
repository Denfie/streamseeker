# Daten-Location

## Grundregel

**Alle Runtime-Daten liegen unter `~/.streamseeker/`** — nichts mehr im
Projekt-Ordner. Zugriff ausschließlich über
[`streamseeker.paths`](../src/streamseeker/paths.py). Kein hardcoded
`"logs/…"` / `"downloads/…"` im Code.

## Layout

```
~/.streamseeker/
├── config.json                      # User-Einstellungen
├── config.credentials.json          # API-Keys (chmod 600, ab Paket G)
├── logs/
│   ├── download_queue.json          # persistente Queue
│   ├── daemon.pid                   # ab Paket D
│   ├── daemon.log                   # ab Paket D
│   ├── daemon.err                   # ab Paket D
│   ├── success.log
│   ├── error.log
│   ├── unsupported_providers.json
│   └── filemoon_debug.json
├── library/                         # ab Paket A
│   ├── index.json
│   ├── <stream>/<slug>.json
│   └── <stream>/<slug>/             # Asset-Ordner (ab Paket G)
│       ├── poster.jpg
│       ├── backdrop.jpg
│       └── seasons/…
├── favorites/                       # ab Paket A
│   ├── index.json
│   └── <stream>/<slug>.json + Assets
├── extension/                       # ab Paket H (Load-Unpacked-Ziel)
└── downloads/                       # per config.json.output_folder umlenkbar
    └── <type>/<name>/Season X/*.mp4
```

## Override per Environment-Variable

`STREAMSEEKER_HOME` setzt den Wurzelpfad auf einen beliebigen Ordner um. Haupt-
einsatzzwecke:
- **Tests**: `monkeypatch.setenv("STREAMSEEKER_HOME", str(tmp_path))`
- **Multi-Profile**: `STREAMSEEKER_HOME=~/.streamseeker-work streamseeker run`
- **Portable Setup**: Auf einem USB-Stick mit eigenem Datenbaum

## `downloads/` weitergeleitet

Der `output_folder` aus `config.json` wird speziell behandelt:

- Leer oder fehlend → `~/.streamseeker/downloads/`
- Relativer Pfad → Relativ zu `~/.streamseeker/` aufgelöst (nicht zu CWD!)
- Absoluter Pfad → unverändert übernommen (für externe Platten, NAS, …)

Das ist sinnvoll, weil Medien oft groß sind und User sie auf separatem Storage
haben wollen. Die JSON-Metadaten bleiben trotzdem klein und zentral bei
`~/.streamseeker/`.

## Migration für bestehende Nutzer

Wer vorher mit Projekt-relativen `logs/` und `downloads/` gearbeitet hat, ruft
nach dem Update einmalig auf:

```bash
streamseeker migrate           # zeigt Plan, fragt nach Bestätigung
streamseeker migrate --dry-run # zeigt Plan, ohne etwas zu tun
streamseeker migrate --force   # ohne Nachfrage
```

Das verschiebt `logs/`, `downloads/`, `config.json` und
`config.credentials.json` per `shutil.move` nach `~/.streamseeker/`.
Existiert das Ziel bereits, wird die Quelle **nicht** überschrieben — der
Migrationsplan zeigt solche Fälle als `[skip]`, damit man manuell entscheiden
kann.

Implementierung: [migrate.py](../src/streamseeker/console/commands/migrate.py).

## API-Referenz

Alle Zugriffe laufen über `streamseeker.paths`:

```python
from streamseeker import paths

paths.home()                        # ~/.streamseeker/
paths.config_file()
paths.credentials_file()
paths.logs_dir()
paths.queue_file()
paths.daemon_pid_file()
paths.daemon_log_file()
paths.daemon_err_file()
paths.unsupported_providers_file()
paths.filemoon_debug_file()
paths.library_dir()
paths.library_index_file()
paths.favorites_dir()
paths.favorites_index_file()
paths.extension_dir()
paths.downloads_dir()               # berücksichtigt config.json.output_folder
paths.series_dir("library", "aniworldto", "oshi-no-ko")
paths.series_file("library", "aniworldto", "oshi-no-ko")
paths.ensure_runtime_dirs()         # legt logs/, library/, favorites/ an
paths.legacy_project_root()         # für migrate-Command
```
