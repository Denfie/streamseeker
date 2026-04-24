# ADR 0007: TMDb als Primär-Quelle für TV-Serien und Filme

- **Status:** accepted
- **Datum:** 2026-04-23

## Kontext
Für Library/Favoriten werden Metadaten (Beschreibung, FSK, Poster, Backdrop,
Genre, Rating) gebraucht, die die Stream-Seiten nicht sauber liefern. Plex,
Jellyfin und Emby nutzen als Standard TMDb + TVDB. Wir brauchen eine
vergleichbare Quelle, die (a) kostenlos, (b) mehrsprachig (insb. Deutsch), (c)
gut dokumentiert ist.

## Entscheidung
**The Movie Database (TMDb)** ist die Primär-Quelle für:
- `sto` (TV-Serien) → `/search/tv`
- `megakinotax` (Filme) → `/search/movie`

TMDb braucht einen kostenlosen API-Key (v3). Er wird in
`~/.streamseeker/config.credentials.json` unter `tmdb_api_key` abgelegt.

Fehlt der Key, fällt der Resolver lautlos auf Minimal-Metadaten zurück — keine
harten Crashes.

## Alternativen
- **OMDb (wrappt IMDb):** schlechtere Artwork-Qualität, weniger mehrsprachige
  Beschreibungen, limitierte Free-Tier.
- **IMDb-Scraping:** ToS-Verletzung, brüchig.
- **TVDB:** sehr gut für TV, schwächer für Filme und Anime. Wird als optionale
  Sekundär-Quelle vorgesehen, nicht primär.

## Konsequenzen
- Neue Dep (kein neues Paket — `requests` reicht).
- User muss einen API-Key registrieren. Einmaliger Aufwand; TMDb ist dafür
  kostenlos und unproblematisch.
- Rate-Limits (~50 req/s) sind für unseren Use-Case unkritisch.
- **Offen:** Falls TMDb irgendwann eingestellt wird oder API-Key-Pflicht
  verschärft → Resolver-Schnittstelle (`MetadataProvider`) macht Ersatz leicht.
