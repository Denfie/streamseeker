# StreamSeeker — Chrome/Brave/Edge Extension

Browser-Add-on, das StreamSeeker direkt auf den unterstützten Stream-Seiten
(`aniworld.to`, `s.to`) einblendet. Die Extension kommuniziert
ausschließlich mit dem lokalen **StreamSeeker-Daemon** auf
`http://127.0.0.1:8765` — ohne laufenden Daemon ist sie nutzlos.

## Voraussetzungen

- StreamSeeker CLI **≥ 0.2.0** (erste Version mit FastAPI-Daemon).
- Daemon läuft im Hintergrund:

  ```bash
  streamseeker daemon start
  # optional:
  streamseeker daemon install-autostart
  ```

## Installation (MVP — Load Unpacked)

1. `chrome://extensions/` öffnen.
2. **Entwicklermodus** aktivieren (rechts oben).
3. **Entpackte Erweiterung laden** und diesen Ordner (`extension/`) wählen.
4. Fertig — auf einer Serien- oder Film-Seite der unterstützten Anbieter
   erscheinen die Badges neben dem Titel.

Auto-Install gibt's in **Paket H** via `streamseeker install-extension`.

## Was du im UI siehst

### Auf Serien-Seiten
- **★ / ☆** neben dem Titel — Favorit toggle.
- **Sammlungs-Badge** neben dem Titel — aggregierter Status über alle
  Staffeln (vollständig / teilweise / leer).
- **Pro Staffel-Link** — Badge mit Fortschritt `3/12` und Status-Icon.
  Klick reiht die komplette Staffel zur Bearbeitung ein.
- **Pro Episoden-Link** — Status-Icon; Klick reiht genau die Episode ein.

### Popup (Klick auf das Extension-Icon)
- **Status** — aktive Vorgänge mit Progressbar, Summary, Queue.
- **Sammlung** — durchsuchbare Liste, mit Cover, FSK-Badges, Filtern auf
  Plattform und Favoriten, Detail-Modal mit Metadaten.
- **Settings** — Daemon-Pfade, Provider, max. parallele Aktivitäten,
  TMDb-Key.

## Troubleshooting

| Symptom | Ursache | Abhilfe |
|---|---|---|
| Rote Meldung „Daemon unreachable" | Daemon läuft nicht | `streamseeker daemon start` |
| Popup zeigt „CLI zu alt" | `minCliVersion` > installierte CLI | CLI updaten |
| Keine Badges auf der Seite | Content-Script nicht geladen | Reload + Check `chrome://extensions/` Logs |
| Cover-Bilder fehlen | Noch kein `library refresh` | `streamseeker library refresh --all` |

## Build

- Icon-Varianten (PNG für den Chrome-Manifest-Slot) werden aus
  `icons/streamseeker-master.svg` per `make icons` erzeugt (siehe Paket H).
- Die Dateiversion steht in `manifest.json` → `version`. Kompatibilitäts-
  Anforderungen an die CLI in `minCliVersion`.
- Changelog: `CHANGELOG.md` (separat vom CLI-Changelog, ADR 0006).

## Sicherheit

- Die Extension macht **keine** ausgehenden Requests außer zu `127.0.0.1:8765`
  und den unterstützten Stream-Domains. Siehe `host_permissions` in `manifest.json`.
- Alle Mutationen (Queue, Favoriten, Library) laufen über den Daemon — die
  Extension schreibt **nie** direkt in Dateien.
- Kein Telemetry, keine Analytics.
