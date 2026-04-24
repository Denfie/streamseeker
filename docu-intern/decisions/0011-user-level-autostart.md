# ADR 0011: User-Level-Autostart (kein sudo, kein system-wide)

- **Status:** accepted
- **Datum:** 2026-04-23

## Kontext
Der Daemon soll beim Login automatisch starten. macOS/Linux/Windows bieten dafür
jeweils systemweite und User-Level-Optionen. StreamSeeker ist Single-User;
systemweite Services wären Over-Engineering und würden sudo-Rechte verlangen.

## Entscheidung
Autostart wird auf User-Ebene implementiert:
- **macOS:** `~/Library/LaunchAgents/com.streamseeker.daemon.plist`
  (via `launchctl load -w`).
- **Linux:** `~/.config/systemd/user/streamseeker.service`
  (via `systemctl --user enable --now`). Für Login-unabhängigen Start einmalig
  `loginctl enable-linger $USER` (User-Verantwortung, kein Auto-Setup).
- **Windows:** Task Scheduler primär, `shell:startup`-Shortcut als Fallback.

Das Kommando ist `streamseeker daemon install-autostart` /
`uninstall-autostart`, ohne sudo.

## Alternativen
- **System-wide LaunchDaemon / systemd system unit:** braucht sudo, schreibt in
  `/Library/…` bzw. `/etc/systemd/system/`. Verworfen.
- **Nur manueller Start:** schlechte UX. Verworfen.

## Konsequenzen
- Daemon läuft als User-Prozess → Zugriff auf `~/.streamseeker/` unkompliziert,
  Dateirechte passen automatisch.
- Keine Multi-User-Unterstützung auf demselben Gerät → akzeptabel, weil User
  explizit Single-User gesagt hat.
- Linux-Autostart ohne Login braucht `loginctl enable-linger` (dokumentieren!).
- Windows-Pfad wird in Paket H implementiert (siehe ADR 0013).
