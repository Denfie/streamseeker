# docu-intern — Interne Dokumentation

Diese Dokumentation richtet sich an alle, die StreamSeeker weiterentwickeln —
Menschen wie AI-Assistenten. Sie ist **Deutsch** und wird zusammen mit dem Code
gepflegt. Bei jeder Architekturänderung wandert ein Update in die passende Seite;
Entscheidungen landen als ADR unter `decisions/`.

## Einstieg

1. [architecture.md](architecture.md) — Wie die Teile zusammenspielen
2. [data-model.md](data-model.md) — Queue-, Library- und Favorites-Schemas
3. [data-location.md](data-location.md) — Wo welche Dateien liegen (`~/.streamseeker/`)
4. [flows.md](flows.md) — Download-, Daemon-, Extension-Flows mit ASCII-Diagrammen
5. [streams.md](streams.md) — Aufbau der Stream-Implementierungen und was sie scrapen
6. [conventions.md](conventions.md) — Code-, Pfad-, Naming- und Icon-Regeln
7. [versioning.md](versioning.md) — SemVer, Changelog, Release-Prozess
8. [platform-support.md](platform-support.md) — macOS/Linux first-class, Windows best-effort

## Entscheidungen (ADRs)

Alle nicht-offensichtlichen Architektur-Entscheidungen werden als Architecture
Decision Record festgehalten. Vor dem Anlegen eines neuen ADRs prüfen, ob das
Thema nicht schon abgedeckt ist — dann entweder Status ändern oder ein
Nachfolge-ADR mit `Supersedes: 000X` anlegen.

→ [decisions/README.md](decisions/README.md)

## Gesamt-Entwicklungsplan

Der genehmigte Plan für die aktuelle Feature-Welle (Favoriten, Library, Daemon,
Browser-Extension, externe Metadaten, Distribution) liegt unter
`~/.claude/plans/jolly-foraging-puddle.md` und ist in neun Pakete unterteilt:

| Paket | Status | Inhalt |
|---|---|---|
| 0 | ✓ | Fundament (paths, CLAUDE.md, docu-intern, Migration, Changelog, ADRs) |
| A | ✓ | LibraryStore (dateibasiertes Storage) |
| B | ✓ | Auto-Population bei Downloads |
| C | ✓ | CLI-Commands `favorite`, `library` |
| D | ✓ | FastAPI-Daemon + Autostart (macOS/Linux) |
| E | ✓ | CLI ↔ Daemon-Integration + Live-View |
| G | ✓ | Externe Metadaten (TMDb / AniList) + Cover-Download |
| F | ✓ | Chrome-Extension (SVG-State-Badges) |
| H | ✓ | Distribution (install-extension, Windows-Autostart, Desktop-Icon) |

Aktueller Stand wird in [CHANGELOG.md](../CHANGELOG.md) unter `[Unreleased]`
fortgeschrieben.
