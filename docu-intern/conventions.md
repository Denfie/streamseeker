# Konventionen

## Sprachen

| Zweck | Sprache |
|---|---|
| Code, Kommentare, Docstrings | Englisch |
| Commit-Messages | Englisch (imperativ) |
| CLI-User-Output | Deutsch |
| Inhalt von `docu-intern/` | Deutsch |
| ADRs | Deutsch |
| Datei- und Ordner-Namen | Englisch |

## Icons — immer SVG

**Alles, was ein Icon ist, ist ein SVG.** Keine PNG- oder JPG-Icons in UI-Elementen.

Ausnahmen, die **keine Icons sind**:
- Cover-Artwork (Poster, Backdrops) — diese sind JPG/PNG und Content, kein Icon.
- Chrome-Extension-Manifest verlangt PNG-Varianten (`icons/extension-{16,48,128}.png`)
  → nur diese dürfen PNG sein, und werden aus einer SVG-Quelle via `make icons`
  generiert, nicht von Hand gepflegt.

Begründung in ADR 0005:
- Auflösungs-unabhängig (Retina, 4K)
- Theming via `currentColor` / CSS
- Kleiner Bundle
- Diff-bar im Git

SVG-Quellen leben für die Extension unter `extension/icons/svg/`. Für die CLI
werden SVG-Icons (z.B. für Desktop-Icons in Paket H) aus einem Master-SVG zur
Build-Zeit in plattform-spezifische Formate konvertiert.

## Pfade

- Runtime-Daten → **nur** über `streamseeker.paths`.
- Projekt-Code → Python-Package-Paths, absolut importieren: `from streamseeker.x import Y`.
- Test-Isolation → `STREAMSEEKER_HOME`-Monkeypatching, keine echten Homes in Tests.

## Testing

- `pytest tests/` läuft alles.
- Jede Test-Datei ist in sich isoliert (Singleton-Reset, Env-Override).
- Neue Module bekommen parallel-geschriebene Tests — nicht nachträglich.
- Keine Netzwerk-Requests in Tests. External-HTTP wird mit `responses` gemockt (Paket G).

## Kommentare

- Default: keine Kommentare. Identifier-Namen sollen sprechen.
- Kommentar nur, wenn WARUM nicht-offensichtlich ist (Bugfix-Referenz, Constraint,
  Invariante).
- Keine TODO-/FIXME-Kommentare ohne Ticket-Referenz (es gibt noch kein Ticketing
  → dann besser sofort erledigen).

## Git

- Kleine, fokussierte Commits. Commit-Message: `<verb> <what>` in Englisch, imperativ.
- Keine `[skip ci]`, `--no-verify`, `--amend` auf published commits.
- Branching-Strategie ist aktuell "direkt auf main" — Single-Developer-Setup.

## Naming

- **Stream-Slugs**: kleinbuchstabig, bindestrich-separiert, URL-kompatibel
  (`oshi-no-ko`, `breaking-bad`, `dune-part-two`).
- **Library-Keys**: `<stream>::<slug>` (z.B. `aniworldto::oshi-no-ko`).
- **Dateinamen Downloads**: `<name>-s<N>e<M>-<lang>.mp4`.
- **Asset-Dateinamen Library**: `poster.jpg`, `backdrop.jpg`, `logo.png`,
  `seasons/sXX-poster.jpg`, `seasons/sXXeYY.jpg` — fest, unabhängig von der
  externen Quelle.
