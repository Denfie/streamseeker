# ADR 0014: Desktop-Icon öffnet das Daemon-Dashboard

- **Status:** accepted
- **Datum:** 2026-04-23

## Kontext
Ein Desktop-Icon ist ein starker UX-Anker — Doppelklicken, sehen was los ist.
Die Frage war, **was** das Icon konkret aufruft:
- Ein Terminal mit `streamseeker run`?
- Direkt die Chrome-Extension öffnen?
- Ein natives Fenster?

## Entscheidung
Das Desktop-Icon öffnet das **Daemon-Dashboard** im Browser:
`http://127.0.0.1:8765/`. Der Daemon liefert dort ein eingebettetes HTML, das
dieselben Module wie das Extension-Popup verwendet (Tabs: Status, Library,
Favoriten).

- **macOS:** `~/Desktop/StreamSeeker.command` (Shell-Script mit `open http://…`).
- **Linux:** `~/.local/share/applications/streamseeker.desktop` + Symlink nach
  `~/Desktop/`, `Exec=xdg-open http://…`.
- **Windows:** `.lnk` mit Target = URL.

## Alternativen
- **Terminal mit `streamseeker run` öffnen:** User-feindlich für Nicht-Terminal-
  Leute; auf Windows besonders problematisch.
- **Extension-Popup direkt:** geht nicht ohne geöffnete Chrome-Extension, und
  die Extension ist optional.
- **Eigenes Tauri/Electron-Window:** bläht Repo um ~50 MB und bringt wenig über
  den Browser hinaus. Verworfen.

## Konsequenzen
- Der Daemon muss zusätzlich zum JSON-API einen Static-HTML-Endpoint
  (`GET /`) ausliefern. Dazu eingebettete JS/CSS/SVG — keine separaten
  Static-Folder-Deployments.
- Das Popup und das Dashboard teilen sich Code: gleiches `api.js`, `state.js`,
  Komponenten. Ein Fix fließt in beide.
- Icon-Asset ist SVG (Icon-Regel) → `make icons` konvertiert es zu `.icns`/`.ico`/`.png`.
