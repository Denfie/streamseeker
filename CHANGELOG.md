# Changelog

All notable changes to the StreamSeeker CLI are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
See [docu-intern/versioning.md](docu-intern/versioning.md) for the release process.

The browser extension is released independently; see `extension/CHANGELOG.md`.

## [0.3.0] - 2026-04-29

### Added

- **Circuit-Breaker für die Download-Queue.** Wenn binnen kurzer Zeit
  zu viele Downloads in Folge fehlschlagen (Standard: 5 Fehlschläge in
  10 min), pausiert der Worker den gesamten Queue-Lauf für mehrere
  Stunden (Standard: 4 h) und nimmt erst danach wieder Items auf.
  Schwellen über `circuit_failure_threshold`,
  `circuit_failure_window` und `circuit_pause_seconds` in der
  `config.json` einstellbar. Status (paused/paused_until) wird über
  `GET /status` mitgeliefert; manuelles Aufheben via
  `POST /queue/resume`.

### Changed

- Anpassungen für besseren Datenabruf bei VOE — weniger Fehlversuche,
  wenn der Anbieter zwischendurch zickt.

### Fixed

- Robusterer Datenabruf bei s.to.
- **Sammlung-Card: korrekte Episoden-Totals statt "1/1".** Beim
  Hinzufügen zur Sammlung wird die volle Staffel-/Episodenanzahl
  ermittelt, sodass Karten und Detailansicht direkt `0/10` (oder
  was auch immer korrekt ist) zeigen statt nur die Anzahl bereits
  geladener Episoden.

### Added

- **Library-Stub + Auto-Enrichment beim Enqueue.** Sobald eine
  Episode/Serie/Film in die Queue geht, legt der Daemon synchron einen
  minimalen Library-Eintrag an (Titel = Slug-Heuristik) und stößt im
  Hintergrund TMDb/AniList-Anreicherung + Season-Total-Fetch an. Die
  Sammlung zeigt die Serie damit sofort mit Cover/Beschreibung/FSK an,
  statt erst nach Abschluss des ersten Downloads. Spiegel der Logik,
  die Favoriten-Add seit jeher nutzt.
- **`LibraryStore.update_season_totals(key, counts)`** — schreibt nur
  `episode_count` pro Saison, ohne `downloaded`-Arrays anzufassen.
  Wird vom Stub-Worker und kann auch manuell zum Backfill genutzt
  werden (`from streamseeker.daemon.server import
  _populate_season_totals`).
- **`/library/{key}/refresh` und `/library/refresh-all` ziehen jetzt
  auch die echten Season-Totals.** Beim Klick auf "Metadaten neu laden"
  (im Detail-Overlay oder Settings) werden zusätzlich zur
  TMDb/AniList-Anreicherung `stream.search_seasons`/`search_episodes`
  aufgerufen, damit alte Library-Einträge endlich `2/62` statt `2/2`
  anzeigen. Filme (`type=='filme'`) und Season 0 (s.to-Filmsektion)
  werden übersprungen.

- Datenabruf bei s.to an aktuellen Stand der Webseite angepasst.
  FSK/PG-Filter davon nicht betroffen.

### Added

- **`/library/refresh-all/status` und `/library/refresh-all/cancel`**.
  Erstes liefert `{running, current, total, success, started_at,
  finished_at, cancel_requested}` für die Popup-Progressbar; zweites
  setzt ein Cancel-Flag, das der Background-Worker am Anfang jeder
  Iteration prüft und sauber abbricht. Nicht-blockierend, idempotent.

### Changed

- **`enqueue_missing` überspringt Saison 0** (s.to-Filme bzw. Specials
  bei aniworldto). Die "Fehlende Episoden"-Aktion soll ausschließlich
  reguläre TV-Episoden einreihen — Filme laufen über `type='filme'`.

### Added

- **`StreamseekerHandler.enqueue_missing()` + neuer `scope: "missing"`**
  für `POST /queue`. Reiht alle Episoden einer Serie ein, die weder im
  Library-Eintrag als `downloaded` markiert sind noch bereits in der
  Queue stehen. Filme werden nur eingereiht, wenn nicht bereits
  vorhanden / in Queue.
- **TMDb-Metadaten zweisprachig.** Der TMDb-Provider holt nun für jede
  Serie/Film zwei Sprachen: `en-US` als Top-Level (Universal-Fallback)
  und `de-DE` als Translation unter `external.tmdb.translations.de`.
  Cover-URLs sind sprachneutral und werden weiterhin nur einmal gecacht.
  AniList bietet keine offizielle Übersetzungs-API → bleibt bei der
  Original-Description (meist Englisch).
- **`localize_block(block, language)`** in
  `streamseeker.api.core.metadata.base` — Helper, der `title`,
  `overview`, `genres`, `tagline` aus `translations[lang]` überlagert
  und auf Top-Level zurückfällt. Spiegel-Implementierung in
  `extension/popup/popup.js` für die Detail-Ansicht.
- **`POST /library/refresh-all`** — paced Bulk-Refresh über alle
  Library-Einträge. Query-Params `reset` (default `true`) und `delay`
  in Sekunden (default `1.5`). Läuft im Hintergrund-Thread, gibt sofort
  `{"queued": N, "delay_seconds": X}` zurück. Vom Extension-Popup
  über den neuen "Metadaten neu laden"-Button im Settings-Tab
  ausgelöst.
- **`POST /updates/dismiss-all`** — räumt sämtliche `pending_updates`
  über die ganze Library in einem Aufruf ab. Genutzt vom neuen
  "Alle als gelesen markieren"-Button im Extension-Popup. Idempotent
  (gibt `{"dismissed": 0}` zurück, wenn nichts ansteht).
- **Browser-Extension auto-sync beim Daemon-Start.** Wenn die im CLI-Paket
  gebundelte Extension-Version neuer ist als die installierte unter
  `~/.streamseeker/extension/`, ersetzt der Daemon den Disk-Copy
  automatisch (atomar via Temp-Dir + Rename, mit `.bak`-Sicherung). Der
  Background-Worker der Extension pollt `GET /extension/version` und
  reloadet sich selbst bei Versionssprung — End-User müssen also nichts
  mehr manuell tun. Symlinks bleiben unangetastet, damit der Dev-Modus
  via `install-extension --link` weiterläuft.
- **`install-extension --link`** für Entwickler: erzeugt einen Symlink
  von `~/.streamseeker/extension/` zur Quelle im Repo. File-Edits sind
  damit ohne erneutes Copy live; ein Klick auf "Reload" in
  `chrome://extensions/` reicht.
- **Neue Daemon-Endpoints:** `GET /extension/version` (genutzt vom
  Background-Worker für Self-Reload). `GET /version` enthält jetzt
  zusätzlich `extension`-Feld.

### Fixed

- **`/events` (SSE) schickt alle 20s eine Keepalive-Kommentarzeile.**
  Verhindert, dass der MV3-Service-Worker der Browser-Extension bei
  ruhiger Queue nach 30s ohne Netzwerk-Traffic eingefroren wird —
  vorher konnte das dazu führen, dass spät geöffnete Tabs keine
  Live-Updates mehr bekamen.

### Added

- **Daemon-Watchdog gegen Hänger.** Neuer Thread im Daemon pingt
  alle 30s den eigenen `GET /health`-Endpoint. Nach 3 aufeinander
  folgenden Fehlern (Timeout, Connection refused, 5xx) ruft der
  Watchdog `os._exit(1)` auf — launchd (`KeepAlive=true`) bzw.
  systemd (`Restart=always`) starten den Daemon dann automatisch
  neu. Behebt das Symptom, dass ein deadlocked Daemon "lebt", aber
  keine Requests mehr beantwortet. Neue Konfiguration in den
  Autostart-Templates: launchd `ThrottleInterval=15`/`ExitTimeOut=30`,
  systemd `StartLimitBurst=5`/`StartLimitIntervalSec=60` damit ein
  echter Crash-Loop nicht eskaliert. Wer Autostart bereits installiert
  hat, muss einmal `streamseeker daemon install-autostart` neu
  ausführen, damit die neuen Throttle-Limits aktiv werden.
- **i18n: Deutsch + English umschaltbar.** Neues Modul
  `streamseeker.i18n` mit JSON-basierten Locale-Bundles unter
  `src/streamseeker/locales/{de,en}.json`. Aktive Sprache wird beim
  Daemon-/CLI-Start aus `config.json` (`language`) gezogen und live
  beim `PATCH /settings` umgeschaltet. CLI-Outputs (Sammlung-Add,
  Skip-Hinweise, Verarbeitungs-Fehler), FFmpeg-Meldungen und
  Daemon-Logs gehen jetzt durch `t("key", **vars)`. Unterstützte
  Sprachen via `i18n.SUPPORTED_LANGUAGES`; weitere Locales lassen sich
  rein additiv per zusätzlichem JSON-Bundle einhängen.
- **Daemon-Endpoint:** `GET /settings` liefert jetzt
  `supported_languages`; `language` ist in der Whitelist von
  `PATCH /settings` (`config.language: "de"|"en"`). Unbekannte Codes
  werden serverseitig verworfen.

### Security

- **11 Dependabot-Alerts geschlossen** — Dependency-Minima in
  `pyproject.toml` so hochgezogen, dass alle aktuell betroffenen
  Versionen ausgeschlossen sind:
    - `Pillow >=12.2.0,<13` (FITS GZIP-Bomb GHSA-pp2g-v4x7-f2qw,
      PSD OOB-Write GHSA-2j2x-2gpw-g8fm)
    - `requests >=2.33.0,<3` (.netrc-Leak, Temp-File-Reuse)
    - `pytest >=9.0.3,<10` (tmpdir-Race)
    - Explizite transitive Pins: `urllib3 >=2.6.3,<3`
      (Decompression-Bomb CVE-2025-50182) und `h11 >=0.16.0,<1`
      (Chunked-Encoding CVE-2025-43859) — obwohl transitiv, pinnen wir
      sie direkt, damit dependabot sie nicht immer wieder flagged.

### Changed

- **Poetry raus, PEP 621 rein.** `pyproject.toml` nutzt jetzt den
  Standard-`[project]`-Table; Build-Backend ist `hatchling`. `poetry.lock`
  und alle `poetry`/`poetry-core`-Referenzen sind weg. Install jetzt via
  `pipx install git+https://github.com/Denfie/streamseeker.git` (End-
  User) oder `pip install -e '.[dev]'` aus einem Checkout (Dev).
  `Makefile`-Targets arbeiten ohne `poetry run` direkt mit
  `python -m streamseeker` / `pytest`. `docs/index.md` mit venv-Cheatsheet
  statt Poetry-Troubleshooting. `get_version()`-Fallback liest jetzt
  `[project].version` (mit Legacy-`[tool.poetry]`-Fallback).

### Fixed

- **pipx-Install funktioniert jetzt.** `get_version()` hat vorher
  `pyproject.toml` aus einem relativen Checkout-Pfad gelesen und in
  jedem installierten Paket (pipx, pip, wheel) mit `FileNotFoundError`
  hart gecrashed — der CLI-Start war damit komplett unmöglich. Jetzt
  primär via `importlib.metadata.version("streamseeker")`, Checkout-
  Fallback nur wenn das Paket nicht installiert ist.

### Performance

- **Content-Script-Check (`GET /library/state`) blockiert nicht mehr
  während Downloads.** Wenn mehrere Downloads parallel laufen und
  Post-Success-Enrichment-Threads die Library-Lock halten, wartete das
  Endpoint ggf. sekundenlang und das Einfärben auf aniworld.to/s.to
  dauerte. Der Endpoint hat jetzt einen 2-s-TTL-Cache pro
  `(stream, slug)`; Write-Pfade (POST/DELETE auf `/queue`, `/favorites`,
  `/library/mark`, pause/resume/retry) invalidieren den Cache
  zielgerichtet. SSE-Push versorgt die UI weiterhin mit Live-Updates,
  das Cache-Fenster ist nur für initiale Page-Loads relevant.

### Fixed

- **Library-Index wird nie mehr geschrumpft gespeichert.** Vorher konnte
  ein stummer Lesefehler oder Multi-Prozess-Race dazu führen, dass ein
  Schreibvorgang einen fast leeren Index zurückschrieb und der User
  plötzlich nur noch 2 statt 56 Serien in der Sammlung sah. Die
  Per-Serien-JSONs auf Platte sind jetzt durchgängig als Quelle der
  Wahrheit anerkannt: `LibraryStore._update_index_row` und
  `_remove_index_row` rufen `_self_heal` auf, das den Index aus den
  Dateien neu aufbaut, sobald die Cache-Größe kleiner als die
  Datei-Anzahl ist. `_read_index` fällt bei fehlender/korrupter
  `index.json` ebenfalls auf Rebuild zurück. Zusätzlich verifiziert ein
  neuer `startup`-Hook im Daemon den Index bei jedem Start.

## [0.2.0] — 2026-04-24

### Added

- Central path module `streamseeker.paths` — all runtime data now resolves under
  `~/.streamseeker/` (overridable via `STREAMSEEKER_HOME` environment variable).
- `streamseeker migrate` command — moves legacy in-project `logs/`, `downloads/`,
  `config.json` and `config.credentials.json` to `~/.streamseeker/`. Supports
  `--dry-run` and `--force` flags.
- Project-level `CLAUDE.md` and `docu-intern/` tree with architecture, data-model,
  flows, conventions, versioning docs and an ADR log.
- `LibraryStore` (new module `streamseeker.api.core.library`): thread-safe,
  file-based storage for Library and Favorites entries with atomic writes and
  a compact search index per kind. Public API: `add`, `remove`, `get`, `list`,
  `search`, `mark_episode_downloaded`, `mark_movie_downloaded`,
  `move_favorite_to_library`, `rebuild_index`. Keys follow the `<stream>::<slug>`
  convention; per-series JSON lives under
  `~/.streamseeker/<kind>/<stream>/<slug>.json` with assets alongside.
- Auto-population of the Library on successful downloads: `DownloadManager`
  records completed episodes/movies via `LibraryStore` when a queue item
  finishes. Best-effort — library write failures never abort the downloader.
- CLI commands for favorites and library management:
  `streamseeker favorite add|remove|list|search|promote` and
  `streamseeker library list|search|show|stats|remove`. All operate directly on
  `~/.streamseeker/library/` and `~/.streamseeker/favorites/`.
- FastAPI-based background daemon listening on `http://127.0.0.1:8765`. New
  Python dependencies: `fastapi`, `uvicorn[standard]` (and `httpx` for tests).
  HTTP endpoints: `GET /version`, `GET /status`, `GET/POST /queue`,
  `GET /library`, `GET /library/{key}`, `GET /library/state`, `GET/POST/DELETE
/favorites`, `POST /favorites/{key}/promote`, `GET /events` (SSE), plus a
  minimal `GET /` HTML dashboard. CORS is open for `localhost` and
  `chrome-extension://` origins.
- Daemon lifecycle commands: `streamseeker daemon start|stop|status|logs` with
  a double-fork background mode and a `--foreground` flag for LaunchAgent/
  systemd. `start` waits until the HTTP server actually accepts connections
  before returning.
- User-level autostart via `streamseeker daemon install-autostart` and
  `daemon uninstall-autostart`. macOS writes
  `~/Library/LaunchAgents/com.streamseeker.daemon.plist`; Linux writes a
  systemd user unit under `~/.config/systemd/user/streamseeker.service`.
  Windows is deferred to Paket H per ADR 0013.
- `daemon_client` HTTP wrapper and `LibraryBackend` facade: every CLI mutation
  now routes to the daemon when it's alive (single-writer rule), and falls
  back to the local store/manager when it isn't. Applies to
  `favorite add|remove|list|search|promote`, `library list|search|show|remove`,
  the `download` wizard's enqueue paths and the `run` live view.
- `streamseeker.cli_api` is now a public Python facade for external scripts:
  `enqueue()`, `status()`, `favorite_add()`, `library_list()`,
  `library_state()`, `events()` — transparent about whether it uses the
  daemon or the local store.
- External metadata enrichment (Plex-style): new module
  `streamseeker.api.core.metadata` with `TmdbProvider`, `AniListProvider` and
  a `MetadataResolver` that picks the right source per stream
  (`aniworldto` → AniList, `sto` → TMDb TV, `megakinotax` → TMDb Movie).
  Posters and backdrops are downloaded, re-encoded to JPEG via Pillow, and
  stored under `~/.streamseeker/library/<stream>/<slug>/{poster,backdrop}.jpg`.
  Filenames are fixed so the UI layer can derive paths without config lookup.
- TMDb key is read from `~/.streamseeker/config.credentials.json`
  (`tmdb_api_key`); missing keys are treated as "provider unavailable" and
  skipped silently. AniList needs no key.
- New CLI command `streamseeker library refresh [<stream> <slug> | --all]`
  and daemon endpoints `POST /library/{key}/refresh`,
  `GET /library/{key}/poster`, `GET /library/{key}/backdrop`.
- `DownloadManager.report_success` now kicks off an opportunistic background
  enrichment after each completed download. Failures never propagate.
- New dependencies: `Pillow>=11` (image re-encoding). Test deps: `responses`.
- `streamseeker library rescan` command — walks
  `~/.streamseeker/logs/success.log` and rebuilds Library entries for
  downloads that happened before the auto-populate hook existed. Run
  `library refresh --all` afterwards to pull TMDb/AniList metadata and
  covers. Idempotent — re-running never duplicates progress.
- `streamseeker daemon restart` command as a shortcut for stop + start.
- `DownloadHelper` now reads/writes `success.log` / `error.log` through the
  `streamseeker.paths` API instead of CWD-relative `logs/` paths. Migrated
  installations keep working without any extra step.
- Chrome extension (separate versioning — see [extension/CHANGELOG.md](extension/CHANGELOG.md)):
  ships as "Load Unpacked" Manifest V3 bundle in the [extension/](extension/)
  folder. Renders SVG-only state badges on series/movie pages of the three
  supported stream providers, plus a popup with Status/Library/Favoriten tabs.
  Requires the daemon to be running.
- Distribution commands: `streamseeker install-extension` copies the extension
  bundle to `~/.streamseeker/extension/` and opens `chrome://extensions/`
  (supports `--update` / `--no-open`); `uninstall-extension` cleans it up.
  `streamseeker install-desktop-icon` creates a Desktop shortcut opening the
  daemon dashboard (macOS `.command`, Linux `.desktop` + Desktop symlink,
  Windows `.lnk` via PowerShell). `uninstall-desktop-icon` removes it.
  `streamseeker uninstall [--purge] [--force]` stops the daemon, removes
  autostart + desktop icon + extension, and optionally deletes
  `~/.streamseeker/` entirely.
- Windows autostart via `schtasks.exe` — `daemon install-autostart` now works
  on Windows, registering an `ONLOGON` task running
  `python -m streamseeker daemon start --foreground` at login.
- Icon rendering helper: `make icons` runs `scripts/render_icons.py` to
  produce the PNG sizes needed by the Chrome manifest and a `.ico`/`.icns`
  bundle from the master SVG. CairoSVG is used when available for fidelity;
  otherwise a Pillow placeholder fallback keeps the build reproducible.

### Changed

- Download queue view in `run` command now groups non-active items by series title
  (e.g. `Dandadan (7)`) instead of listing every episode individually — prevents
  terminal overflow when large queues are loaded.
- `DownloadManager.QUEUE_FILE`, `ProviderFactory.UNSUPPORTED_FILE` and
  `FilemoonProvider.DEBUG_FILE` class attributes removed; all file I/O now goes
  through `streamseeker.paths`.
- `StreamseekerHandler` resolves `output_folder` config to an absolute path against
  `~/.streamseeker/` at startup, so streams always receive an unambiguous path
  regardless of the current working directory.

### Internal

- Test suite runs against a temporary `STREAMSEEKER_HOME` — no test writes to the
  real user home anymore.

## [0.1.5] — 2026-04-11

### Added

- Queue-based download orchestration via `DownloadManager` and `QueueProcessor`.
- `retry` command to re-queue failed downloads.

### Fixed

- Various logging improvements and provider bug fixes.

## [0.1.4] and earlier

Baseline releases; history predates this changelog.
