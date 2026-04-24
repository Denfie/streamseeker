# ADR 0009: Cover lokal speichern, kein Hotlinking

- **Status:** accepted
- **Datum:** 2026-04-23

## Kontext
Cover-Bilder werden oft angezeigt (Popup, Dashboard, Content-Script-Hover).
TMDb/AniList-CDN direkt laden wäre einfach, hat aber Nachteile: sichtbare
Ladezeiten, Netz-Abhängigkeit (kein Offline-Browsing), Tracking durch CDNs,
Rate-Limits auf Abrufe.

## Entscheidung
Alle Cover werden beim ersten Fetch heruntergeladen und in der **Serien-
Folder-Struktur** abgelegt:

```
~/.streamseeker/library/<stream>/<slug>/poster.jpg
~/.streamseeker/library/<stream>/<slug>/backdrop.jpg
```

Beim Download wird via `Pillow` auf JPEG Q=85, max ~500 KB re-encodiert.
Dateinamen sind **fest** (`poster.jpg`, `backdrop.jpg`, …) — unabhängig von der
externen Quelle. Im Library-JSON wird nur der relative Dateiname abgelegt, nie
eine URL.

Re-Fetch erfolgt **on-demand** via `streamseeker library refresh <key>` —
automatische TTL-Expiry wäre für unseren Use-Case (seltene Updates) Overkill.

## Alternativen
- **Nur URL speichern (Hotlinking):** kleiner auf Disk, aber Offline-Nutzung
  unmöglich und Rate-Limit-Risiko.
- **Cache in separatem `covers/`-Baum mit Hash-Namen:** funktioniert, aber
  entkoppelt Assets von der Serie → Aufräumen bei `remove` aufwändiger. Verworfen.

## Konsequenzen
- Neue Dep: `Pillow` (für Re-Encoding, Resize, Format-Konvertierung).
- Hardlink-Mirror in `downloads/` (Plex-Style) wird zum Low-Cost-Feature, weil
  die Bilder ohnehin lokal sind (siehe Paket G).
- Disk-Usage: ~1 MB pro Serie (Poster + Backdrop). Bei 1000 Serien ≈ 1 GB —
  überschaubar.
- Lösch-Operation: beim `library remove` muss zusätzlich zum JSON der Asset-
  Ordner mit-gelöscht werden. Wird in `LibraryStore.remove()` gekapselt.
