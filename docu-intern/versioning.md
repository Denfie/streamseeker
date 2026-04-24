# Versionierung & Release-Prozess

## Zwei unabhängige Versionsstränge

| Artefakt | Quelle der Wahrheit | Changelog | Tag-Präfix |
|---|---|---|---|
| CLI / Backend | `pyproject.toml` (`version = "0.2.0"`) | [CHANGELOG.md](../CHANGELOG.md) | `v0.2.0` |
| Chrome-Extension | `extension/manifest.json` (`"version": "0.1.0"`) | `extension/CHANGELOG.md` | `ext-v0.1.0` |

Warum zwei Stränge: CLI und Extension sind unabhängig releasable. Ein reiner
UI-Fix in der Extension muss nicht das CLI-Release aufhalten, und umgekehrt
(siehe ADR 0006).

## Kompatibilitäts-Deklaration

Jede Extension-Version deklariert in `manifest.json` per Custom-Key
`"minCliVersion"` die Mindest-CLI. Das Popup vergleicht beim Start mit
`GET /version` vom Daemon und zeigt ein Banner, wenn die CLI älter ist:

```json
{
  "name": "StreamSeeker",
  "version": "0.1.0",
  "minCliVersion": "0.2.0"
}
```

## SemVer-Regeln

- **MAJOR**: Breaking Change in Daemon-API, Queue-Schema, Library-Schema oder CLI-Commands.
- **MINOR**: Neues Feature, neuer Command, neuer Endpoint — rückwärtskompatibel.
- **PATCH**: Bugfixes, Performance, Doku.

Beispiele:
- Neuer Endpoint `GET /library/state` → MINOR
- Umbenennung eines Library-JSON-Felds → MAJOR
- Fix in `standard.py`-Downloader → PATCH

## Release-Flow (CLI)

```bash
# 1. Version heben
vim pyproject.toml       # version = "0.2.0"

# 2. Changelog abschließen
vim CHANGELOG.md         # ## [0.2.0] — YYYY-MM-DD unter [Unreleased]

# 3. Commit + Tag
git add pyproject.toml CHANGELOG.md
git commit -m "Release 0.2.0"
git tag v0.2.0

# 4. Push
git push && git push --tags
```

## Release-Flow (Extension)

```bash
vim extension/manifest.json      # "version": "0.1.1"
vim extension/CHANGELOG.md       # ## [0.1.1] — YYYY-MM-DD
git add extension/
git commit -m "Release extension 0.1.1"
git tag ext-v0.1.1
git push && git push --tags
```

## Publikation

- **CLI**: für End-User via `pipx install streamseeker` (PyPI). Publishing-Details
  kommen mit Paket H.
- **Extension**: im MVP per "Load Unpacked" (siehe [platform-support.md](platform-support.md)).
  Chrome-Web-Store ist später eine Option, nicht Teil des MVP (ADR 0012).

## "[Unreleased]"-Block

Jedes Paket, das Code ändert, trägt seine Neuerungen in den `[Unreleased]`-Block.
Beim nächsten Tag wird der Block unter seine neue Versionsnummer verschoben, und
ein frischer `[Unreleased]` entsteht. Konvention-Abschnitte:

- `### Added`
- `### Changed`
- `### Deprecated`
- `### Removed`
- `### Fixed`
- `### Security`
- `### Internal` (non-user-facing, aber für Contributors wichtig)
