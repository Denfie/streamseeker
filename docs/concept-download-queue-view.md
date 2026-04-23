# Konzept: Download-Queue mit View-Switching

## Problem

Downloads laufen als Background-Threads mit tqdm-Progressbars. Die Bars und die interaktiven Cleo-Menüprompts schreiben gleichzeitig auf die Konsole und erzeugen kaputte Ausgabe. Es fehlt die Möglichkeit, während laufender Downloads neue Suchen zu starten und frei zwischen Menü und Download-Ansicht zu wechseln.

## Ziele

1. **Frei wechseln** zwischen Menü-Modus und Download-Ansicht (beliebig oft hin und her)
2. **Queue-basiert**: Alle Downloads gehen in eine persistente Queue. Neue Suchen fügen weitere Downloads hinzu
3. **Saubere Ausgabe**: tqdm-Bars stören nicht die Menü-Prompts
4. **Jederzeit beenden**: Unfertige Downloads bleiben in der Queue für `make retry`
5. **Fortsetzen**: `make retry` nimmt da auf wo man aufgehört hat

## Kernidee: Bars standardmäßig ausgeblendet

Progressbars sind **nur in der Download-Ansicht sichtbar**. Im Menü-Modus sind sie deaktiviert (`tqdm.disable=True`). Status-Meldungen (✅ Erfolg / ❌ Fehler) erscheinen immer über `tqdm.write()` — in beiden Modi.

## Interaktions-Flow

```
┌─────────────────────────────────────────────────────┐
│                    HAUPTMENÜ                         │
│                                                     │
│  [2 downloading | 3 queued | 1 failed]              │
│                                                     │
│  [ 0] Download a movie or show                      │
│  [ 1] View downloads              ← dynamisch      │
│  [ 2] About us                                      │
│  [ 3] -- Quit --                                    │
│                                                     │
│  ✅ naruto-s1e5-german.mp4         ← tqdm.write()  │
│  ❌ naruto-s1e7-german.mp4         ← erscheint     │
│     auch im Menü-Modus                              │
└─────────────────────────────────────────────────────┘
         │                    │                │
         ▼                    ▼                ▼
   "Download"          "View downloads"     "Quit"
         │                    │                │
         ▼                    ▼                ▼
┌─────────────┐   ┌──────────────────┐  ┌──────────┐
│ Such-Wizard │   │ DOWNLOAD-ANSICHT │  │ Graceful  │
│             │   │                  │  │ Exit      │
│ Show?       │   │ Bars AKTIVIERT   │  │           │
│ Season?     │   │                  │  │ Warten?   │
│ Language?   │   │ file1: 45%|████  │  │ [y/N]     │
│ Provider?   │   │ file2: 78%|█████ │  │           │
│             │   │ file3: 12%|██    │  │ N → Queue │
│ → startet   │   │                  │  │     bleibt│
│   Threads   │   │ ✅ file4.mp4     │  │ Y → warte │
│ → zurück    │   │                  │  │     auf   │
│   zum Menü  │   │ [m] Menü        │  │     alle  │
│             │   │ [q] Quit         │  └──────────┘
└─────────────┘   │ [Enter] Refresh  │
                  └──────────────────┘
                           │
                     "m" gedrückt
                           │
                           ▼
                  ┌─────────────────┐
                  │   HAUPTMENÜ     │
                  │   Bars AUS      │
                  │   Kann wieder   │
                  │   "View" oder   │
                  │   "Download"    │
                  │   wählen        │
                  └─────────────────┘
```

## Download-Ansicht: Steuerung

In der Download-Ansicht hat der User drei Optionen:

| Taste   | Aktion                                        |
|---------|-----------------------------------------------|
| `m`     | Zurück zum Menü (Bars werden ausgeblendet)    |
| `q`     | App beenden (wie "Quit" im Menü)              |
| `Enter` | Ansicht auffrischen (Terminal clearen, Bars neu zeichnen) |

### Implementierung der Tastenabfrage

```python
import sys
import select

def _read_key(timeout=0.5) -> str | None:
    """Non-blocking key read mit Timeout (macOS/Linux)."""
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if ready:
        return sys.stdin.readline().strip().lower()
    return None
```

### Download-Ansicht Loop

```python
def _show_download_view(self):
    manager = DownloadManager()
    manager.show_bars()

    while True:
        # Header anzeigen
        summary = manager.queue_summary()
        self.line("")
        self.line("<fg=cyan>--- Download Progress ---</>")
        self.line(f"  ⬇ {summary['downloading']}  |  ⏳ {summary['pending']}  |  ❌ {summary['failed']}")
        self.line("")
        self.line("<comment>[m] Menu  [q] Quit  [Enter] Refresh</comment>")

        # Warte auf Eingabe (tqdm rendert frei während wir warten)
        key = input().strip().lower()

        match key:
            case "m" | "":  # m oder Enter
                if key == "m":
                    break  # zurück zum Menü
                # Enter = Refresh: Terminal clearen und weiter
                print("\033[2J\033[H", end="")  # ANSI clear screen
            case "q":
                manager.hide_bars()
                self._graceful_quit()
                return "quit"
            case _:
                pass  # ignorieren, weiter in der Ansicht

    manager.hide_bars()
```

**Hinweis:** `input()` ist die einfachste Lösung. Der User tippt einen Buchstaben + Enter. tqdm-Bars rendern währenddessen frei im Terminal. Für eine Lösung mit einzelnem Tastendruck ohne Enter bräuchte man `termios` (raw mode) — das ist optional und komplexer.

## DownloadManager Erweiterungen

### Neue Felder

```python
class DownloadManager(metaclass=Singleton):
    def __init__(self):
        self._lock = threading.Lock()
        self._active_positions: set[int] = set()
        self._downloads: list[dict] = []
        self._retry_contexts: dict[str, dict] = {}
        self._active_bars: dict[int, tqdm] = {}    # NEU: Bar-Tracking
        self._bars_visible: bool = False             # NEU: Sichtbarkeit
```

### Neue Methoden

```python
def register_bar(self, pos: int, bar: tqdm) -> None:
    """Registriert eine tqdm-Bar für View-Switching."""
    with self._lock:
        self._active_bars[pos] = bar

def unregister_bar(self, pos: int) -> None:
    """Entfernt eine tqdm-Bar nach Abschluss."""
    with self._lock:
        self._active_bars.pop(pos, None)

def show_bars(self) -> None:
    """Aktiviert alle Progressbars (Download-Ansicht)."""
    with self._lock:
        self._bars_visible = True
        for bar in self._active_bars.values():
            bar.disable = False
            bar.refresh()

def hide_bars(self) -> None:
    """Deaktiviert alle Progressbars (Menü-Modus)."""
    with self._lock:
        self._bars_visible = False
        for bar in self._active_bars.values():
            bar.disable = True

def bars_visible(self) -> bool:
    """Abfrage ob Bars gerade sichtbar sein sollen."""
    return self._bars_visible

def queue_summary(self) -> dict:
    """Gibt Zusammenfassung der Queue zurück."""
    queue = self._load_queue()
    return {
        "downloading": len(self._active_positions),
        "pending": sum(1 for q in queue if q.get("status") == "pending"),
        "failed": sum(1 for q in queue if q.get("status") == "failed"),
    }
```

## Downloader-Änderungen (ffmpeg.py + standard.py)

Jeder Downloader registriert seine tqdm-Bar beim Manager und respektiert die Sichtbarkeit:

```python
# Bei Bar-Erstellung:
pbar = tqdm(
    ...,
    disable=not self._manager.bars_visible(),  # NEU
    file=sys.stderr,                            # NEU: Trennung von Cleo (stdout)
)
self._manager.register_bar(pos, pbar)           # NEU

# Bei Bar-Abschluss (vor pbar.close()):
self._manager.unregister_bar(pos)               # NEU
pbar.close()
```

## Hauptmenü Änderungen (run.py)

```python
while True:
    manager = DownloadManager()
    manager.hide_bars()  # Bars immer AUS bevor Menü gezeigt wird

    active = manager.active_count()
    if active > 0 or has_queue_items:
        summary = manager.queue_summary()
        self.line(f"<info>[⬇ {summary['downloading']} | ⏳ {summary['pending']} | ❌ {summary['failed']}]</info>")

    # Dynamisches Menü
    choices = ["Download a movie or show"]
    if active > 0 or has_queue_items:
        choices.append("View downloads")
    choices.append("About us")
    choices.append("-- Quit --")

    search_type = self.choice(...)

    match search_type:
        case "Download a movie or show":
            self.call("download")       # Wizard → startet Threads → zurück
        case "View downloads":
            result = self._show_download_view()
            if result == "quit":
                return 0
        case "-- Quit --":
            self._graceful_quit()
            return 0
```

## Graceful Quit

```python
def _graceful_quit(self):
    manager = DownloadManager()
    active = manager.active_count()
    if active > 0:
        wait = self.confirm(
            f"{active} download(s) running. Wait for them to finish?",
            default=False
        )
        if wait:
            self.line("<comment>Waiting for downloads...</comment>")
            manager.show_bars()
            manager.wait_all()
            manager.hide_bars()
            self.line("<info>All downloads completed.</info>")
        else:
            self.line("")
            self.line("<comment>Unfinished downloads remain in the queue.</comment>")
            self.line("<comment>Run 'make retry' to resume later.</comment>")
```

## Persistente Queue: Lebenszyklus eines Downloads

```
1. User wählt "Download" → Wizard → handler.download()
   → Item wird in download_queue.json geschrieben (status: "pending")
   → Thread wird gestartet

2a. Download erfolgreich:
    → ✅ Meldung via tqdm.write()
    → Item wird aus Queue ENTFERNT
    → Eintrag in success.log

2b. Download fehlgeschlagen (nach 3 Retries):
    → ❌ Meldung via tqdm.write()
    → Item bleibt in Queue (status: "failed", attempts: 3)
    → Eintrag in error.log

2c. App wird beendet:
    → Laufende Downloads sterben (daemon threads)
    → Items bleiben in Queue (status: "pending" oder "in_progress")

3. make retry:
    → Liest Queue
    → Filtert bereits heruntergeladene (success.log Check)
    → Setzt status auf "in_progress"
    → Startet Downloads für verbleibende Items
```

## Queue-Datei Format (logs/download_queue.json)

```json
[
  {
    "stream_name": "aniworldto",
    "provider": "voe",
    "name": "my-hero-academia-vigilantes",
    "language": "german",
    "type": "staffel",
    "season": 2,
    "episode": 1,
    "file_name": "downloads/anime/my-hero-academia-vigilantes/Season 2/...-s2e1-german.mp4",
    "status": "pending",
    "attempts": 0,
    "added_at": "2026-03-17T10:44:21+01:00"
  }
]
```

## Betroffene Dateien

| Datei | Änderung |
|-------|----------|
| `api/core/downloader/manager.py` | Bar-Tracking, show/hide, queue_summary |
| `api/core/downloader/ffmpeg.py` | Bar registrieren, `disable` Flag, `file=sys.stderr` |
| `api/core/downloader/standard.py` | Bar registrieren, `disable` Flag, `file=sys.stderr` |
| `console/commands/run.py` | "View downloads" Menüpunkt, View-Loop, hide_bars, Graceful Quit |
| `console/commands/retry.py` | `mark_in_progress` vor Download-Start |

## Was sich NICHT ändert

- Download-Wizard (AniworldtoDownloadCommand) bleibt unverändert
- tqdm + Cleo als Libraries bleiben
- Daemon-Threads bleiben
- Auto-Retry (3x intern) bleibt
- success.log / error.log Logik bleibt
- Makefile retry Target bleibt

## Offene Entscheidungen

1. **Tasteneingabe**: `input()` (einfach, braucht Enter) vs. `termios` raw mode (einzelner Tastendruck, komplexer). Empfehlung: Erstmal `input()`, kann später aufgerüstet werden.
2. **Queue-Limit**: Soll es ein Maximum an gleichzeitigen Downloads geben? Aktuell: unbegrenzt (limitiert durch DDOS-Timer).
3. **Auto-View**: Soll nach dem Start eines Downloads automatisch die Download-Ansicht gezeigt werden? Oder immer zurück zum Menü?
