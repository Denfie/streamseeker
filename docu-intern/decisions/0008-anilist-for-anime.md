# ADR 0008: AniList als Primär-Quelle für Anime

- **Status:** accepted
- **Datum:** 2026-04-23

## Kontext
Für Anime ist TMDb lückenhaft — viele Titel fehlen oder sind unter englischen
Ausstrahlungs-Namen gelistet. `aniworldto` ist unser einziger Anime-Stream und
braucht eine bessere Quelle.

## Entscheidung
**AniList** ist die Primär-Quelle für den Stream `aniworldto`. AniList hat eine
offene GraphQL-API ohne API-Key für Lesezugriffe.

## Alternativen
- **MyAnimeList via Jikan:** funktioniert, aber Jikan ist ein inoffizieller Wrapper
  und hat Rate-Limits, die aggressiver sind. Wird als Sekundär-Option vorgehalten.
- **Nur TMDb auch für Anime:** schlechte Match-Qualität (fehlende Titel, falsche
  Zuordnung zu live-action).

## Konsequenzen
- GraphQL-Client mit `requests.post` reicht — keine neue Dep.
- Kein API-Key nötig → kein Setup für den User.
- Rate-Limit 90 req/min → unkritisch, mit Semaphore leicht einzuhalten.
- Anime-spezifische Felder (seasonYear, episodeDuration, Studio) werden im
  `external.anilist`-Teil des Library-Schemas abgelegt.
