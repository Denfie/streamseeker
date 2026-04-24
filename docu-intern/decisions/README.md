# Architecture Decision Records (ADRs)

Jede nicht-offensichtliche Architektur-Entscheidung bekommt einen ADR. Nummern
werden fortlaufend vergeben und nie wiederverwendet — auch wenn ein ADR später
verworfen wird (Status: `superseded`).

## Template

```markdown
# ADR 000X: <Titel>

- **Status:** accepted | superseded
- **Datum:** YYYY-MM-DD
- **Supersedes:** ADR 000Y (optional)
- **Kontext:** Problem, Constraints, Umgebung.
- **Entscheidung:** Was konkret gewählt wurde.
- **Alternativen:** Verworfene Optionen + kurze Begründung pro Option.
- **Konsequenzen:** Was die Entscheidung impliziert; was später neu zu bewerten wäre.
```

## Index

| # | Titel | Status |
|---|---|---|
| [0001](0001-file-based-library.md) | Library pro Serie in eigener JSON | accepted |
| [0002](0002-minimal-metadata.md) | Minimal-Metadaten statt extern anreichern (initial) | superseded |
| [0003](0003-fastapi-daemon.md) | FastAPI + uvicorn für den Daemon | accepted |
| [0004](0004-daemon-optional.md) | CLI bleibt ohne Daemon voll funktional | accepted |
| [0005](0005-svg-only-icons.md) | Icons ausschließlich als SVG | accepted |
| [0006](0006-independent-versioning.md) | CLI und Extension unabhängig versioniert | accepted |
| [0007](0007-tmdb-primary-source.md) | TMDb als Primär-Quelle für TV/Filme | accepted |
| [0008](0008-anilist-for-anime.md) | AniList als Primär-Quelle für Anime | accepted |
| [0009](0009-local-image-cache.md) | Cover lokal speichern, kein Hotlinking | accepted |
| [0010](0010-user-home-data-dir.md) | Alle Daten unter `~/.streamseeker/` | accepted |
| [0011](0011-user-level-autostart.md) | User-Level-Autostart (kein sudo/system-wide) | accepted |
| [0012](0012-unpacked-extension-install.md) | Chrome-Extension als "Load Unpacked" | accepted |
| [0013](0013-windows-best-effort.md) | Windows als best-effort, nicht first-class | accepted |
| [0014](0014-desktop-icon-opens-dashboard.md) | Desktop-Icon öffnet Daemon-Dashboard | accepted |
