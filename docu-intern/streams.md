# Streams

## Basisklasse

[stream_base.py](../src/streamseeker/api/streams/stream_base.py) definiert das
Interface, das jede Stream-Implementierung erfüllt:

| Methode | Zweck | Rückgabe |
|---|---|---|
| `search(name)` | Serien-Übersicht | `{types, movies, series}` |
| `search_seasons(name, type)` | Staffel-Nummern | `list[int]` |
| `search_episodes(name, type, season)` | Episoden-Nummern | `list[int]` |
| `search_providers(name, type, season, episode)` | Verfügbare Hoster | `dict[provider_name, {title, url, ...}]` |
| `search_details(name, type, season, episode)` | Episoden-Meta | `dict` |
| `seach_languages(...)` | Sprachen (Tippfehler historisch) | `list` |
| `download(...)` | Startet Download | `Downloader`-Instanz |
| `build_file_path(...)` | Ziel-Dateipfad | `str` |
| `is_downloaded(file_name)` | Lokal-Check | `bool` |
| `download_successfull(file_name)` | Erfolg loggen | — |
| `download_error(...)` | Fehler loggen | — |

## Konkrete Implementierungen

### aniworld.to — `aniworldto/aniworldto.py`
Anime. Types: `staffel`, `filme`. Scraped Poster-Grid, Episoden-Tabelle, Sprache,
Provider-Buttons. Year via `<span itemprop="startDate">`.

### s.to — `sto/sto.py`
TV-Serien. Struktur sehr ähnlich zu aniworldto (gleicher Website-Betreiber).
Types: `staffel`, `filme`. Legt Downloads unter `downloads/serie/<name>/…` ab.

### megakino.tax — `megakinotax/megakinotax.py`
Kinofilme. Einfachere Struktur: keine Staffeln, nur Filme. `ask_movie()` in
`commands/download.py` holt Titel + Description mit.

## Was die Streams an Metadaten liefern (kostenlos)

| Feld | aniworldto | sto | megakinotax |
|---|---|---|---|
| Titel (Deutsch) | ✓ | ✓ | ✓ |
| Slug | ✓ | ✓ | ✓ |
| Jahr | ✓ | ✓ | – |
| Staffel-Anzahl | ✓ | ✓ | n/a |
| Episoden pro Staffel | ✓ | ✓ | n/a |
| Beschreibung | – | – | ✓ |
| Cover-Bild | (HTML da) | (HTML da) | (HTML da) |
| FSK/Genre | – | – | – |

**Merksatz:** Alles über Basis-Strukturdaten hinaus (Poster, FSK, Beschreibung,
Rating) sollte **nicht** aus dem Stream geholt werden, sondern über den
`MetadataResolver` aus Paket G (TMDb / AniList). Grund: wir haben dann konsistente
Daten in jeder Sprache und müssen Stream-HTML-Parser nicht für Metadaten
aufblähen.

## Einen neuen Stream hinzufügen

1. Neues Verzeichnis `src/streamseeker/api/streams/<name>/`
2. Klasse von `StreamBase` erben und die Abstrakten implementieren
3. Falls nötig, neue Provider unter `api/providers/` ergänzen
4. In `api/streams/streams.py` registrieren
5. Tests unter `tests/test_build_file_path.py` ergänzen
6. CLI-Wizard (`commands/download.py`) erkennt den Stream automatisch
