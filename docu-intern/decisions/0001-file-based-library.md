# ADR 0001: Library pro Serie in eigener JSON

- **Status:** accepted
- **Datum:** 2026-04-23

## Kontext
Die Library braucht eine persistente Datenhaltung für 10–1000+ Serien. Der User
hat explizit keine DB (MySQL/PostgreSQL) gewünscht — Einzelnutzer-Setup auf
lokalem Gerät. Drei realistische Optionen standen zur Auswahl.

## Entscheidung
Pro Serie eine eigene JSON-Datei unter
`~/.streamseeker/library/<stream>/<slug>.json`, ergänzt durch eine
`index.json` im Library-Root für schnelle Übersicht/Suche.

## Alternativen
- **Eine große `library.json` mit allen Einträgen:** einfacher zu implementieren,
  aber bei 100+ Serien wird jedes Save zu einem kompletten JSON-Rewrite. Parallel-
  Schreibvorgänge (Daemon + CLI) wären unsicher ohne File-Locking.
- **SQLite als `library.db`:** einzelne Datei, durchsuchbar via SQL, keine extra
  Deps (stdlib `sqlite3`). Verworfen, weil User "dateibasiert" wollte und SQLite
  für den Use-Case (überschaubare Menge, zufällige Einzelupdates) Over-Engineering
  wäre. Zudem: Git-Diffs auf `.db` sind nutzlos, auf JSON lesbar.

## Konsequenzen
- **Gut:** Einzelne Einträge sind unabhängig editierbar/löschbar. Git-freundlich
  für manuelle Backups. Parallel-Writes betreffen verschiedene Dateien.
- **Weniger gut:** Listen-Operationen (alle Einträge lesen) müssen viele Dateien
  öffnen oder den `index.json` pflegen. Letzteres macht `LibraryStore` —
  jede Änderung aktualisiert atomar Index + Einzeldatei.
- Falls später >10k Serien → Neubewertung mit SQLite-Option (neuer ADR).
