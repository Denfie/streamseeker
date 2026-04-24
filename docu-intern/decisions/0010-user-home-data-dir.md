# ADR 0010: Alle Daten unter `~/.streamseeker/`

- **Status:** accepted
- **Datum:** 2026-04-23

## Kontext
Vor dem Umbau lagen Runtime-Daten (Queue, Downloads, Logs, Config) im Projekt-
Ordner. Das ist problematisch, sobald die CLI systemweit via `pipx` installiert
wird: das "Projekt" ist dann z.B. `~/.local/pipx/venvs/streamseeker/…`, und
Daten dorthin zu schreiben wäre falsch. Außerdem skaliert es nicht, wenn man
den CLI-Checkout ersetzt.

## Entscheidung
Alle Runtime-Daten liegen unter einem einzigen Wurzelverzeichnis:
- **Default:** `~/.streamseeker/`
- **Override:** ENV-Variable `STREAMSEEKER_HOME`

Zugriff ausschließlich über [`streamseeker.paths`](../../src/streamseeker/paths.py).
Kein hardcoded `"logs/…"` mehr im Code.

## Alternativen
- **XDG-konformer Split** (`$XDG_CONFIG_HOME/streamseeker`,
  `$XDG_DATA_HOME/streamseeker`, `$XDG_CACHE_HOME/streamseeker`): korrekt nach
  Linux-Konvention, aber drei Orte verwirren bei einfacher Einzel-User-Nutzung
  und machen Backups schwieriger. **Verworfen** zugunsten eines einzigen Pfads.
- **`~/Library/Application Support/StreamSeeker/` (macOS-Style)**: nur auf macOS
  konvention, nicht plattform-neutral. Verworfen.
- **`./data/` relativ zum CWD**: verbietet pipx-Install und macht Tests instabil.
  Verworfen.

## Konsequenzen
- **Gut:** Eine klare Stelle fürs Backup (`tar ~/.streamseeker/`), konsistent
  über Plattformen. Multi-Profile via `STREAMSEEKER_HOME`-Override möglich.
- **Migration nötig:** bestehende User hatten Daten im Projekt-Ordner. Dafür
  existiert der `streamseeker migrate`-Command (Paket 0.3).
- Wer XDG-Konvention braucht, setzt `STREAMSEEKER_HOME=$XDG_DATA_HOME/streamseeker`.
- Test-Isolation ist trivial: `monkeypatch.setenv("STREAMSEEKER_HOME", tmp_path)`.
