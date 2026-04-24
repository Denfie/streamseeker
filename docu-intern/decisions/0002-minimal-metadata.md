# ADR 0002: Minimal-Metadaten (initial) — später ersetzt durch externe Quellen

- **Status:** superseded (ersetzt durch ADR 0007 + 0008)
- **Datum:** 2026-04-23

## Kontext
Beim Entwurf der Library wurde zunächst entschieden, nur die Metadaten zu
speichern, die die Streams ohne zusätzliche Requests liefern (Titel, Jahr,
Staffel-/Episoden-Anzahl). Cover, Beschreibung, FSK, Genre wurden **abgewählt**,
um den MVP klein zu halten.

## Entscheidung
Die erste Library-Version speichert nur Minimal-Felder. Das Schema wird so
angelegt, dass Erweiterungen (Feld `external`) später additiv möglich sind.

## Alternativen
- Sofort externe Quellen (TMDb/AniList) anbinden → siehe ADR 0007/0008
  (nachträglich doch gewählt).

## Konsequenzen
- Kurz nach dieser Entscheidung hat der User gesagt: "Metadaten und Bilder
  sollten über eine Movie DB aus dem Internet abgefragt werden (wie Plex)."
- Dieser ADR wird deshalb auf `superseded` gesetzt. ADR 0007 (TMDb) und ADR 0008
  (AniList) ersetzen ihn.
- Das Schema bleibt korrekt: `external` ist optional, fehlt bei älteren
  Einträgen einfach.
