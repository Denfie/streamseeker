# Changelog — StreamSeeker Browser Extension

Separate from the CLI changelog (`CHANGELOG.md` at the repo root). Extension
and CLI versions are independent (ADR 0006). The extension declares its
required CLI version via the `minCliVersion` key in `manifest.json`.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.15.2] — 2026-04-25

### Changed
- **Settings-Tab: "Downloads" → "Sammlung".** Pfad-Label ("Sammlung"
  statt "Downloads"), Sektionstitel ("Sammlung" statt "Downloads") und
  Feldlabel ("Max. parallele Aktivitäten" statt "Max. parallele
  Downloads"). Disk-Pfad bleibt `~/.streamseeker/downloads/` — nur die
  UI-Beschriftung ändert sich, damit nichts an existierenden Daten
  bricht.

## [0.15.1] — 2026-04-25

### Fixed
- **Speichern-Button im Settings-Tab geht jetzt über die volle
  Containerbreite** — vorher schmiegte er sich nur an seine eigene
  Textbreite, die Sektionen oben drüber waren full-width. Status-Text
  rutscht eine Zeile unter den Button.

## [0.15.0] — 2026-04-25

### Added
- **Settings-Tab** (⚙) im Popup. Zeigt Daemon-Pfade (Home, Downloads,
  Library, Config) und erlaubt das Editieren der wichtigsten Werte:
  Bevorzugter Provider, max. parallele Downloads, max. Retries und
  TMDb-API-Key. Backend-Endpoints `GET /settings` (gibt **keinen**
  Klartext-Key zurück, nur Boolean-Flag) und `PATCH /settings` mit
  Whitelist-validierten Schreibfeldern. TMDb-Key landet weiterhin in
  `~/.streamseeker/config.credentials.json` mit `chmod 600`.

### Fixed
- **Header zeigt jetzt sowohl Extension- als auch CLI-Version**
  (`ext 0.15.0 · CLI 0.2.0`). Vorher überschrieb der Daemon-Version-Fetch
  die zuvor gesetzte Extension-Version.

## [0.14.0] — 2026-04-25

### Added
- **📁 Sammlung öffnen-Button im Detail-Modal.** Vierter Icon-Button in
  der Tool-Reihe (`↻ 🔎 📁 🗑`). Triggert
  `POST /library/{key}/open-folder`; der Daemon resolvt den Pfad in
  `~/.streamseeker/downloads/<type>/<slug>/` und öffnet ihn
  plattformspezifisch (`open` auf macOS, `xdg-open` auf Linux,
  `explorer` auf Windows). Fällt bei nicht existentem Ordner auf den
  Parent zurück, statt 500 zu werfen.

## [0.13.4] — 2026-04-24

### Fixed
- **Episoden-Tabelle auf s.to wird wieder eingefärbt.** Das neue
  s.to-Layout (2026+) verzichtet auf das anchor-wrapped Row-Pattern —
  stattdessen sind Zeilen `<tr class="episode-row" onclick="window.location='/serie/<slug>/staffel-N/episode-M'">`.
  Das Content-Script iteriert jetzt zusätzlich über
  `[onclick*="/episode-"]`, liest Season+Episode aus dem `onclick`-Attribut
  und wrappt die Episoden-Nummer in `.ss-ep-badge`. Andere Spalten
  (Titel, Hoster, Sprache) bleiben unverändert.

## [0.13.3] — 2026-04-24

### Fixed
- **s.to-Content-Script wieder funktionsfähig.** s.to hat den URL-Prefix
  für Serien von `/serie/stream/<slug>` auf `/serie/<slug>` geändert,
  wodurch `parseLocation()` kein Slug mehr gezogen hat und sämtliche
  Badges/Icons unsichtbar blieben. Regex akzeptiert jetzt beide Formen
  (`/serie(?:/stream)?/<slug>`). `STREAM_URL_BUILDERS.sto` im Popup
  zielt ebenfalls auf das neue Schema.

## [0.13.2] — 2026-04-24

### Fixed
- **Suche in der Sammlung filterte nicht.** Selber Root-Cause wie beim
  Detail-Modal in 0.11.1: `.card { display: grid }` hat das
  `hidden`-Attribut überschrieben, also blieben die Karten sichtbar
  egal was im Suchfeld stand. Jetzt explizit via
  `.card[hidden] { display: none !important }` gehidet. Titel + Slug
  werden ohnehin schon als Needle gematcht (partial, case-insensitive).

## [0.13.1] — 2026-04-24

### Changed
- **Action-Leiste im Detail-Modal neu gelayoutet** — statt einer langen
  Knopfreihe jetzt drei Ebenen:
  1. Großer Primär-Button "Auf … öffnen" (volle Breite).
  2. Kompakte Icon-Reihe mit `↻ 🔎 🗑` (gleichverteilt, quadratisch).
  3. Provider-Chips (`TMDB ↗`, `ANILIST ↗`, …) darunter, wrappen bei
     Bedarf.

## [0.13.0] — 2026-04-24

### Added
- **Eintrag aus Sammlung entfernen:** Neuer 🗑 Entfernen-Button im
  Detail-Modal. Löscht via `DELETE /library/{key}` den
  Sammlungs-Eintrag + Cover-Ordner. Heruntergeladene Videos unter
  `~/.streamseeker/downloads/` bleiben erhalten (Schutz vor
  versehentlichem Datenverlust). Bestätigungs-Dialog vor dem Löschen.

### Fixed
- **Nur das Modal scrollt, nicht mehr der Hintergrund.** `html` + `body`
  bekommen beim Öffnen `overflow: hidden !important; height: 100%`,
  sodass der Popup-Content darunter fixiert bleibt. `.detail` selbst
  scrollt intern (`overflow-y: auto` + `overscroll-behavior: contain`).

## [0.12.0] — 2026-04-24

### Added
- **Suche anpassen**-Button im Detail-Modal (🔎 Suche). Klick öffnet ein
  Mini-Formular mit Titel- und Jahr-Input; "Suchen & Ersetzen" triggert
  `POST /library/{key}/refresh?title=…&year=…&reset=true`, damit man
  mehrdeutige Slugs (z.B. `stargate` → Stargate SG-1 statt dem 2025er
  Remake) manuell auf den richtigen Treffer lenken kann.
- **Gap-Fill in der Detail-Anzeige:** Felder werden jetzt aus *allen*
  Provider-Blöcken zusammengezogen — fehlt TMDb das Rating aber TVmaze
  hat eins, wird TVmaze' Rating angezeigt. Reihenfolge TMDb > AniList >
  OMDb > TVmaze > Jikan; erster nicht-leerer Wert gewinnt pro Feld.
- **FSK-Circle-Badges in der Sammlung** (0 weiß, 6 gelb, 12 grün, 16
  blau, 18 rot). Quelle ist der erste Provider-Block mit `fsk`-Feld —
  in der Praxis kommt das aus TMDb, erfordert also einen TMDb-Key in
  `~/.streamseeker/config.credentials.json`.

## [0.11.1] — 2026-04-24

### Fixed
- **Detail-Modal verhält sich jetzt wie ein echter Overlay:** `position: fixed`
  statt `absolute`, sodass es das Popup immer komplett überdeckt — egal wie
  weit die Sammlung gescrollt ist. Schließt man das Modal via `×`, kehrt
  der Scroll an die ursprüngliche Position zurück. Die darunter liegende
  Liste ist während der Modal-Anzeige gesperrt (`body.ss-detail-open`).

## [0.11.0] — 2026-04-24

### Fixed
- **Detail-Modal war leer:** `.detail { display: flex }` hat das
  `hidden`-Attribut überschrieben, sodass das Overlay immer sichtbar und
  bei Popup-Öffnen leer war. Jetzt explizit via
  `.detail[hidden] { display: none !important }` gehidet.

### Added
- **Metadaten-Refresh-Button im Detail-Modal** (`↻ Meta`): triggert
  `POST /library/{key}/refresh` und lädt die externen Blöcke neu,
  ohne CLI-Befehl.

## [0.10.0] — 2026-04-24

### Added
- **Detail-Modal im Popup:** Klick auf eine Karte öffnet ein Overlay
  mit Cover, Backdrop, **FSK/USK**-Badge, Rating, Genres, Beschreibung,
  Staffel-/Episoden-Zähler und "Auf Seite öffnen"-Button. Zusätzlich
  Sekundär-Buttons pro Metadaten-Anbieter, die auf dessen Detail-Seite
  springen (TMDb, AniList, TVmaze, Jikan/MAL).
- **Provider-Registry + Fallback-Kette** pro Stream. Konfigurierbar in
  `~/.streamseeker/config.json`:
  ```json
  "metadata_chains": {
    "aniworldto": ["anilist", "jikan", "tmdb"],
    "sto": ["tmdb", "tvmaze"],
    "megakinotax": ["tmdb"]
  }
  ```
  Jeder erfolgreiche Provider-Hit trägt seinen Block zu `external.*`
  bei; der erste Hit besitzt Artwork, alle anderen steuern nur Daten
  (z.B. FSK von TMDb + Studios von AniList).
- **Zwei neue Provider** ohne API-Key-Ballast:
  - **TVmaze** — TV-fokussiert, keyfree, guter TMDb-Fallback für s.to
  - **Jikan** (MyAnimeList) — Anime-Fallback für AniList bei obskuren Titeln
- **Direktlinks zum Provider** — jeder Match speichert jetzt
  `source_url` (z.B. `https://anilist.co/anime/101`) im
  `external.<provider>`-Block; Detail-Modal zeigt sie als Sprungziel.

### Fixed
- Auf der Serien-Startseite (URL ohne `/staffel-N/`, z.B.
  `/anime/stream/dragonball-gt`) wurden Episoden-Links nicht
  eingefärbt. Der Content-Script extrahiert jetzt die Staffel direkt
  aus jedem Anchor-href statt nur aus `location.pathname`.

## [0.9.0] — 2026-04-24

### Added
- **Bestand markieren** im "Zur Sammlung hinzufügen"-Modal. Umschalter
  oben im Modal zwischen **⬇ Herunterladen** und **✓ Bestand
  markieren**. Letzterer Modus fügt Episoden als "vorhanden" in die
  Sammlung ein, ohne einen Download auszulösen — ideal für User, die
  schon viele Episoden auf Platte haben und die Sammlung nachträglich
  auffüllen wollen. Der Update-Checker erkennt sie danach genauso.
- Neuer Daemon-Endpoint `POST /library/mark` (akzeptiert dieselben
  Scope-Werte wie `/queue`: `single/season/season_from/from/all`) plus
  automatisches Metadata-Enrichment nach dem Markieren.

## [0.8.0] — 2026-04-24

### Changed
- **Sammlung + Favoriten sind nun eine Liste.** Favorit ist ein Flag auf
  dem Library-Eintrag statt eines separaten Speichers. Der Favoriten-
  Tab im Popup ist weg; stattdessen:
  - Filter-Chip **⭐ Favoriten** in der Sammlung (schaltbar an/aus)
  - Stern-Button rechts auf jeder Karte togglet Favorit direkt
  - Die Overlay-Kebab-Aktion "Favorisieren" bleibt unverändert bedienbar
- Update-Scheduler checkt jetzt nur noch eine Liste — doppelte Scrape-
  Requests für Einträge, die vorher in beiden Kinds waren, entfallen.
- Update-Check-Throttle von 5s auf 2s pro Eintrag.

### Migrated
- Alte `~/.streamseeker/favorites/*`-Dateien (JSONs + Cover) werden
  beim nächsten Daemon-Start automatisch in `~/.streamseeker/library/`
  eingespielt, mit `favorite: true`. Der `favorites/`-Ordner wird
  anschließend entfernt. Keine Aktion nötig.

### API
- `/favorites`-Endpoints bleiben als dünne Shims funktional
  (Back-Compat für ältere Extension-Builds): POST setzt `favorite: true`,
  DELETE setzt `favorite: false`, GET liefert Library-Einträge mit Flag.
- `POST /favorites/:key/promote` ist ein No-op, gibt den bestehenden
  Library-Eintrag zurück — nichts mehr zu verschieben.

## [0.7.0] — 2026-04-24

### Added
- **Neu-Tab** im Popup mit Badge-Zähler: zeigt Serien/Filme aus Sammlung
  oder Favoriten, bei denen seit der letzten Prüfung neue Staffeln,
  Episoden oder Filme auf der Stream-Seite aufgetaucht sind. Der Daemon
  scraped automatisch alle 24 Stunden die getrackten Einträge und merkt
  sich die Änderungen in `pending_updates`.
- Auto-Fokus-Logik beim Popup-Öffnen: **Neu** (wenn Updates da sind) →
  **Status** (wenn Queue nicht leer) → sonst **Sammlung**.
- Sternchen-Icon (★) in Sammlung- und Favoriten-Karten, wenn für den
  Eintrag offene Updates vorliegen — klar sichtbar ohne Tab-Wechsel.
- Update-Karten zeigen konkrete Diffs ("neue Staffel 4", "S3: +2
  Episoden", "neuer Film") mit einem ✓-Button zum Abnicken. Klick auf
  die Karte springt direkt zur Stream-Seite.
- Neue Daemon-Endpoints `GET /updates` + `POST /updates/:key/dismiss` +
  `POST /updates/check` (manueller Trigger, `?wait=true` für synchron).

## [0.6.0] — 2026-04-24

### Added
- Vollwertiges Scope-Picker-Modal wie im CLI-Wizard. Beim Klick auf
  "Zur Sammlung hinzufügen" im Overlay lädt das Modal die Struktur der
  Serie (`GET /series/:stream/:slug/structure`) und zeigt alle fünf
  Modi: **Komplette Serie**, **Komplette Staffel**, **Staffel ab
  Episode**, **Ab Staffel/Episode**, **Nur diese Episode**. Staffel-
  und Episoden-Dropdowns werden je nach Modus eingeblendet und
  mit Werten aus der URL vorbelegt. Sprache und Provider sind jetzt
  ebenfalls im Modal wählbar — Defaults `german` / `voe`.
- Endpoints `GET /series/:stream/:slug/structure` (Seasons + Sprachen +
  Provider) und `GET /series/:stream/:slug/episodes?season=N` (Episoden
  einer Staffel, lazy-geladen).

## [0.5.12] — 2026-04-24

### Fixed
- "Zur Sammlung hinzufügen" aus dem Overlay-Kebab legte nur Stub-
  Einträge an — Sprache, Provider und realer Zielpfad fehlten, der
  QueueProcessor hatte nichts Brauchbares zum Runterladen. Payload
  enthält jetzt ein explizites `scope`-Feld (`single`/`season`/
  `from`/`all`), der Daemon reicht es an `StreamseekerHandler.enqueue_*`
  durch. Damit werden Episoden wie erwartet in die Queue aufgenommen und
  laufen direkt an.

## [0.5.11] — 2026-04-24

### Fixed
- Im Top-"Episoden:"-Pill-Bar sah der Tint aus wie eine verschachtelte
  Doppelbox (Site-Pill aussen, mein Span innen). Wenn der ganze
  Anker-Text bereits die Folge-Beschriftung ist, wird der Anker jetzt
  direkt getönt — gleicher Ansatz wie bei Staffel-Links. Nur bei
  mehrteiligen Anchors (Tabellenzeile mit Titel + Folge) bleibt der
  Span-Wrap aktiv.

## [0.5.10] — 2026-04-24

### Fixed
- Der Staffel-Selector (`a[href*="/staffel-"]`) matchte auch Episoden-
  Links wie `/staffel-3/episode-1`, wodurch `data-ss-state` auf allen
  Episoden-Anchors der Tabelle landete und die alten anchor-tint-CSS-
  Regeln die komplette Zeile einfärbten. Season-Matching ignoriert
  jetzt Hrefs, die einen `/episode-`-Abschnitt enthalten.

### Changed
- `.ss-ep-badge` mit mehr Atemraum (`padding: 1px 8px`), dezentem
  Margin und sauberer `line-height` — wirkt harmonischer in den
  Tabellenzeilen und im Top-Pill-Bar.

## [0.5.9] — 2026-04-24

### Changed
- Episode-Tinting auf der Seite arbeitet jetzt mit einem umschließenden
  Text-Span (`.ss-ep-badge`) statt das ganze `<a>`-Element einzufärben.
  Auf aniworld wickelt ein Link manchmal die ganze Zeile inkl. Titel-
  und Hoster-Spalten — das führte bisher zu flächigem Grün. Der Span
  wrappt nur noch den "Folge N"-Text, andere Zellen bleiben unberührt.

## [0.5.8] — 2026-04-24

### Fixed
- Status-Tab zeigte Karten beim Popup-Öffnen doppelt / verdreifacht,
  wenn der initiale Render und der erste SSE-Snapshot gleichzeitig
  liefen. `renderStatus` benutzt jetzt einen Generation-Counter und
  verwirft veraltete Renders vor dem Schreiben ins DOM.

## [0.5.7] — 2026-04-24

### Fixed
- Progress-Bar auf den Queue-Karten blieb leer: der Downloader
  registriert Bars mal unter dem vollen Pfad (HTTP-Direct), mal nur
  unter dem Basename (ffmpeg-HLS). Das Popup matcht jetzt beides.

## [0.5.6] — 2026-04-24

### Fixed
- Status-Tab zeigte aktive Downloads doppelt (einmal oben als Progress-
  Zeile, einmal in der Queue-Karte). Die separate Active-Sektion wurde
  entfernt; Progress-Bar + Prozentwert erscheinen jetzt direkt auf der
  zugehörigen Karte.

## [0.5.5] — 2026-04-24

### Changed
- Episode-Tabelle auf aniworld: gezielt nur das erste `<td>` pro Zeile
  der `.seasonEpisodesList` wird getönt. Außerhalb der Tabelle (Top-
  Episoden-Pills etc.) verhalten sich die Tints wie bisher.
- Status-Tab: der ↻-Button steht jetzt auch bei `skipped`-Einträgen zur
  Verfügung und heißt generisch "Neu einreihen" statt "Erneut versuchen".

## [0.5.4] — 2026-04-24

### Fixed
- Episode-tabelle auf aniworld.to: nur die Zelle mit dem "Folge N"-Label
  wird getönt, nicht mehr die zweite Spalte mit dem Episodentitel
  (beide Zellen sind `<a>`-Elemente auf denselben Episoden-Link). Der
  Content-Script filtert jetzt nach Anchor-Text.

## [0.5.3] — 2026-04-24

### Fixed
- Aniworld's `.hosterSiteDirectNav ul li a` has a `color: … !important`
  with higher specificity than our tint rules — season/episode text in
  that nav stayed in the site's original colour. Doubled the
  `[data-ss-state]` attribute selector so our foreground wins.

## [0.5.2] — 2026-04-24

### Removed
- "→ in Sammlung"-Button auf Favoriten-Karten im Popup. Promoten geht
  weiterhin bequem über das Overlay-Kebab-Menü auf der jeweiligen
  Serien-Seite.

## [0.5.1] — 2026-04-24

### Fixed
- Breadcrumb + table rows pointing at the current page no longer get
  tinted — the active episode keeps the site's own styling.
- Brightened the state font colours and cascaded them into inner spans
  so the labels on tinted links stay readable on dark host themes.

## [0.5.0] — 2026-04-24

### Changed
- Host-page colouring: episode links are now only tinted in the first
  column (episode number) — the entire table row is no longer recoloured.
  The "active" season/episode kept by the site's own highlighting is left
  untouched. Font colours on tinted seasons/episodes adjusted so text
  stays readable.
- Orange tint for `pending` / `paused` / `skipped` queue items; the blue
  queued tint is now reserved for actively downloading episodes.

### Added
- Status tab in the popup shows rich cards per queue item: cover,
  title + `SxxEyy` label, status, plus action buttons (pause/resume,
  retry, delete). Click the card to open the specific episode in a new
  tab (e.g. `.../staffel-2/episode-5`).
- Auto-enrichment of newly-added favorites: the daemon triggers metadata
  + cover download in the background when a favorite is added, so the
  popup card gets a poster once the lookup finishes.

## [0.4.0] — 2026-04-24

### Changed
- Popup wording reframed as "Sammlung": tab renamed from "Library" to
  "Sammlung"; "Keine aktiven Downloads." → "Nichts wird gerade gesammelt.";
  "Queue ist leer." → "Keine offenen Einträge."; favorites promote button
  from "→ Library" to "→ in Sammlung".

### Added
- Click a card in the Sammlung- or Favoriten-Tab to open the series page
  in a new tab (aniworld.to / s.to / megakino.tax — URL derived from
  stream + slug).
- Stream-Filter-Chips above the search field in both tabs. Appear only
  when the list contains entries from more than one source. "Alle"
  switches back to the full view.

## [0.3.0] — 2026-04-24

### Changed
- Reframed the overlay as a **collection tracker** rather than a download
  tool. The only obvious button is now "⭐ Merken" (favorites). Advanced
  actions, including the add-to-collection dialog, live behind a discreet
  "⋮" kebab menu.
- Wording toned down throughout: "Download" → "Zur Sammlung hinzufügen",
  "in Queue" → "wird gesammelt", "Library" → "Sammlung".
- Removed the prominent primary-colored Download button.

### Added
- Host-page season and episode links get a subtle background tint based
  on their collection state: green for complete, amber for partial, blue
  for queued, red for failed. Implemented via `data-ss-state` attributes
  set by the content script; CSS lives in `overlay.css`.
- `/library/state` now returns a per-episode status map per season so the
  content script can colour individual episode links without extra calls.

## [0.2.0] — 2026-04-24

### Changed
- Replaced inline per-link badges with a single **fixed bottom-right overlay**.
  Shows the current series title, context (stream, `SxxEyy` if present),
  download status text and "⭐ Favorit" / "📚 Library" markers at a glance.
- The overlay's **Download** button opens a modal with the full scope menu
  that mirrors the CLI wizard: only this episode / whole season / from this
  episode onwards / entire series. Movies show a single "Ganzen Film
  herunterladen" choice.
- Toast notifications (top-center) for favorite add/remove and enqueue
  confirmation, red toast for errors.

### Removed
- `content_scripts/badges.css` — replaced by `overlay.css`.
- Per-season and per-episode inline badges. Equivalent functionality now
  lives behind the modal reached via the overlay's Download button.

### UX
- The overlay can be collapsed via the **−** button; click the minimised
  pill (or the **+**) to expand again. State is persisted in
  `localStorage` so the choice survives page navigation.
- A coloured status dot in front of the title reflects the aggregated
  download state even in the collapsed pill.

## [0.1.0] — 2026-04-24

### Added
- Initial release of the StreamSeeker Chrome extension (Manifest V3).
- Content scripts for `aniworld.to`, `s.to` and `megakino.tax` that render
  inline SVG state badges next to the series title and episode rows:
  favorite (☆/★), download state (⬇ outline / ◐ partial / ⬇ filled / ⟳ queued /
  ✕ failed). Badges refresh live via Server-Sent Events from the daemon.
- Clickable badges trigger daemon API calls: toggle favorite,
  enqueue episode/season for download.
- Popup with three tabs: **Status** (live daemon queue + progress),
  **Library** (search + browse with covers), **Favorites** (search + promote).
- Compatibility check on popup open: warn if the daemon's CLI version is
  older than `minCliVersion`.
- All UI icons are SVG (see ADR 0005). PNG icons in `icons/` are generated
  from the master SVG via `make icons` (Paket H).

### Requires
- StreamSeeker CLI ≥ 0.2.0 (the first version shipping the FastAPI daemon).
- A daemon running on `http://127.0.0.1:8765` — start it with
  `streamseeker daemon start` or install it with
  `streamseeker daemon install-autostart`.
