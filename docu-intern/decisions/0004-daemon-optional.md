# ADR 0004: CLI bleibt ohne Daemon voll funktional

- **Status:** accepted
- **Datum:** 2026-04-23

## Kontext
Der Daemon ist ein großer Zuwachs (eigener Prozess, HTTP-Server, Autostart). Für
User, die nur ab und zu einen Download starten, wäre ein Pflicht-Daemon
Over-Engineering. Andererseits brauchen Browser-Extension und lang-laufende
Hintergrund-Downloads den Daemon.

## Entscheidung
Der Daemon ist **optional**. Jeder CLI-Command funktioniert ohne ihn:

- Daemon aus → CLI nutzt `DownloadManager`/`QueueProcessor` im CLI-Prozess
  (wie heute).
- Daemon an → CLI erkennt ihn (Ping `/status` mit 200 ms Timeout) und leitet
  Mutationen (`enqueue`, `favorite add`, …) per HTTP an ihn. Der QueueProcessor
  läuft dann nur im Daemon, nicht mehr im CLI.

Die Erkennung passiert in `daemon_client.is_daemon_running()`. Jeder Command
kennt beide Pfade.

## Alternativen
- **Daemon-pflicht:** saubere Architektur (ein Single-Writer), aber hohe
  Einstiegshürde. Verworfen.
- **Kein Daemon überhaupt:** Browser-Extension-Anbindung wäre nicht möglich.
  Verworfen.

## Konsequenzen
- Zwei Code-Pfade pro Command (HTTP vs. direkt) — Pflege-Last.
- Abgefedert durch `daemon_client`-Abstraktion, die den richtigen Writer liefert.
- User-Doku muss beide Pfade erwähnen.
- **Regel:** Niemals beide Pfade gleichzeitig schreiben (z.B. Queue-Writer im CLI
  UND Daemon). Wird im CLI-Pfad durch `is_daemon_running()` abgefragt und
  entschieden.
