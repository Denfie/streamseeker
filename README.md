# StreamSeeker

Dein persönlicher Tracker für Serien, Animes und Filme auf **aniworld.to**,
**s.to** und **megakino.tax**. Markiere Favoriten, baue eine eigene Sammlung
auf, sieh auf einen Blick wo es neue Staffeln oder Episoden gibt, und spring
mit einem Klick direkt auf die Serien-Seite.

StreamSeeker besteht aus drei Teilen:

1. **CLI** (Python) — Kernstück, läuft lokal auf macOS, Linux und Windows.
2. **Daemon** — optionaler Hintergrunddienst mit lokaler HTTP-API
   (`http://127.0.0.1:8765`), über den die Browser-Extension spricht.
3. **Chrome-Extension** — zeigt direkt auf aniworld.to / s.to / megakino.tax
   den Status deiner Serien an (Favorit, in Sammlung, neue Episoden) und
   stellt ein Popup mit Detail-Ansicht, Suche und Metadaten bereit.

<p align="center">
  <img src="https://raw.githubusercontent.com/uniprank/streamseeker/master/assets/usage-v-0-1-5.gif" alt="Streamseeker usage" width="800"/>
</p>

## Features

- **Favoriten-Liste** — Serien, Animes oder Filme markieren und jederzeit
  wiederfinden.
- **Eigene Sammlung** — automatisch gepflegt, sortierbar nach Plattform,
  filterbar auf Favoriten.
- **Neu-Erkennung** — ein Background-Check meldet, sobald eine neue Staffel
  oder Episode auf der Quell-Seite erschienen ist. Die Extension zeigt das
  mit einem ⭐-Indikator am Karten-Titel und einem eigenen "Neu"-Tab.
- **Metadaten** — deutsche Overviews, Cover, Backdrop, Rating, Genres und
  FSK-Badges (wenn ein TMDb-Key konfiguriert ist). Provider-Kette pro
  Plattform konfigurierbar: AniList / Jikan / TMDb / TVmaze.
- **Quick-Jump** — Klick auf einen Sammlungs-Eintrag öffnet direkt die
  Seite bei aniworld.to / s.to / megakino.tax.
- **Status-Indikatoren direkt auf der Quell-Seite** — Staffel-Badges,
  Episoden-Icons und Favoriten-Stern werden per Content-Script in die
  Original-Seite eingeblendet.

## Installation

### Voraussetzungen

- **Python 3.11 oder neuer** (macOS / Linux / Windows)
- **[FFmpeg](https://ffmpeg.org)** im `PATH`
  - macOS: `brew install ffmpeg`
  - Linux: `apt install ffmpeg` (oder Äquivalent)
  - Windows: `winget install Gyan.FFmpeg`
- **[Poetry](https://python-poetry.org/docs/#installation)** für Dependency-Management

### StreamSeeker benutzen

Drei Wege: **ohne Install direkt aus dem Checkout**, **pipx** für
systemweite Installation, oder **Poetry** für Entwickler. Nichts davon
schließt sich aus — wenn du schon einen Poetry-Workflow hast, bleibt er
funktionstüchtig.

#### Variante 0 — Ohne Install aus einem Checkout

Wenn du nicht global installieren willst (oder StreamSeeker erstmal nur
probieren):

```bash
git clone https://github.com/uniprank/streamseeker.git
cd streamseeker
python -m pip install -r <(poetry export --without-hashes -f requirements.txt)
python -m streamseeker run
python -m streamseeker daemon start
```

Vorteil: kein `pipx`, kein globaler Launcher. Nachteil: du musst
`python -m streamseeker …` ausführen und im Checkout-Verzeichnis sein
(oder den Pfad im Autostart absolut angeben). Für Autostart über
systemd/launchd ist die pipx-Variante praktischer, weil dort ein
`streamseeker`-Launcher auf dem `PATH` liegt.

#### Variante A — pipx (empfohlen für Endnutzer)

[pipx](https://pypa.github.io/pipx/) installiert CLI-Tools in isolierten
Virtualenvs und legt einen Launcher auf den `PATH`. Einmal installiert
läuft `streamseeker` von überall.

```bash
# pipx einmalig installieren
brew install pipx           # macOS
# oder: python3 -m pip install --user pipx && pipx ensurepath
# oder: apt install pipx    # Ubuntu 23.04+

# StreamSeeker aus dem Git-Repo installieren (ohne Checkout)
pipx install git+https://github.com/uniprank/streamseeker.git

# Update auf die neueste Version
pipx upgrade streamseeker
```

Alternativ aus einem lokalen Checkout:

```bash
git clone https://github.com/uniprank/streamseeker.git
pipx install ./streamseeker
```

Nach der Installation ist `streamseeker` auf dem `PATH` — **keine
`poetry shell`-Session nötig**.

#### Variante B — Poetry (für Entwickler & bestehende Setups)

Nur relevant, wenn du am Code arbeiten oder Tests laufen lassen willst.

```bash
git clone https://github.com/uniprank/streamseeker.git
cd streamseeker
poetry install
poetry shell               # aktiviert das dev-venv
```

Innerhalb der `poetry shell` steht `streamseeker` zur Verfügung. Ohne
`poetry shell` kannst du jeden Befehl auch via `poetry run streamseeker …`
aufrufen.

### Datenablage

StreamSeeker legt alle Runtime-Daten unter `~/.streamseeker/` ab
(Sammlung, Favoriten, Metadaten, Cover, Logs). Der Pfad lässt sich über
die Umgebungsvariable `STREAMSEEKER_HOME` umbiegen.

### Daemon starten

Der Daemon hält die HTTP-API bereit, an die sich die Chrome-Extension
hängt.

```bash
streamseeker daemon start
```

Der Daemon lauscht dann auf `http://127.0.0.1:8765`. Status prüfen:

```bash
streamseeker daemon status
```

Autostart beim System-Login (macOS LaunchAgent / Linux systemd user unit):

```bash
streamseeker daemon install-autostart
```

### Chrome-Extension installieren

```bash
streamseeker install-extension
```

Das Command kopiert die Extension nach `~/.streamseeker/extension/` und
öffnet `chrome://extensions/`. Dort:

1. **Developer Mode** oben rechts aktivieren.
2. **Load Unpacked** klicken.
3. Ordner `~/.streamseeker/extension/` auswählen.
4. Chrome fragt beim ersten Öffnen einer unterstützten Seite nach der
   **Berechtigung, auf die Seite zuzugreifen** (Popup über dem Puzzle-
   Icon bzw. direkt beim ersten Content-Script-Inject). Diesen Zugriff
   einmalig erlauben — sonst bleibt die Seite "stumm" und es erscheinen
   keine Badges/Icons.

Nach der ersten Installation kann es nötig sein, bereits geöffnete
Tabs von aniworld.to / s.to / megakino.tax einmal neu zu laden, damit
die Content-Scripts greifen. Danach: Favoriten-Stern neben dem Serien-
Titel, Staffel-/Episoden-Badges in der Übersicht, Klick aufs Extension-
Icon öffnet das Popup mit Sammlung, Status und Updates.

### Optional: TMDb-API-Key für Metadaten

Damit Cover, deutsche Overviews und FSK-Badges befüllt werden, trage
deinen [TMDb-Key](https://www.themoviedb.org/settings/api) in
`~/.streamseeker/config.credentials.json` ein:

```json
{ "tmdb_api_key": "DEIN_KEY" }
```

AniList, Jikan und TVmaze laufen ohne Key. Fehlt der TMDb-Key, fällt
StreamSeeker lautlos auf die keyfreien Provider zurück.

## CLI-Befehle (Auszug)

```bash
streamseeker run                      # interaktives Hauptmenü
streamseeker library list             # Sammlung als Tabelle
streamseeker library stats            # Zusammenfassung
streamseeker favorite add <stream> <slug>
streamseeker library refresh --all    # Metadaten für alle Einträge neu holen
streamseeker daemon start|stop|status|logs
```

Volle Befehlsliste: `streamseeker --help`.

## Unterstützte Plattformen

- **AniWorld** (aniworld.to)
- **Serie Stream** (s.to)
- **MegaKino** (megakino.tax)

## Rechtlicher Hinweis

StreamSeeker ist ein Werkzeug zur persönlichen Organisation und
Status-Anzeige. Dieses Projekt ist ausdrücklich zu Bildungszwecken
entstanden und zeigt, was mit Python möglich ist. Jede Nutzung für
illegale Zwecke ist untersagt. Der Autor übernimmt keine Haftung für
missbräuchliche Verwendung des Tools.

## Lizenz

MIT — siehe [LICENSE](LICENSE).
