# Changelog

All notable changes to the StreamSeeker CLI are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
See [docu-intern/versioning.md](docu-intern/versioning.md) for the release process.

The browser extension is released independently; see `extension/CHANGELOG.md`.

## [Unreleased]

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
