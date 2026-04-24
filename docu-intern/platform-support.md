# Plattform-Support

## Übersicht

| Plattform | Status | CI-Tests | Desktop-Integration | Autostart |
|---|---|---|---|---|
| macOS 13+ | **first-class** (dev-system) | ja | `.command`-Script | LaunchAgent |
| Linux (systemd) | **first-class** | ja | `.desktop`-Datei | systemd user unit |
| Windows 10/11 | **best-effort** | nein | `.lnk`-Shortcut | Task Scheduler |

First-class = getestet, unterstützt, Bug-Reports bekommen Priorität.
Best-effort = funktioniert in der Regel, aber Edge-Cases werden nicht proaktiv
getestet.

Entscheidung dokumentiert in ADR 0013.

## macOS

- Default-Home: `~/.streamseeker/` (= `/Users/<user>/.streamseeker/`)
- Autostart: `~/Library/LaunchAgents/com.streamseeker.daemon.plist`, aktiviert
  via `launchctl load -w`. `KeepAlive=true` → Auto-Restart bei Crash.
- Desktop-Integration: `~/Desktop/StreamSeeker.command` (Shell-Script öffnet
  Dashboard-URL) mit `.icns`-Icon aus dem Repo.
- Dependencies außerhalb Python: `brew install ffmpeg`.

## Linux (systemd)

- Default-Home: `~/.streamseeker/`.
- Autostart: `~/.config/systemd/user/streamseeker.service`, aktiviert via
  `systemctl --user enable --now`. Für Autostart ohne Login einmalig
  `loginctl enable-linger $USER`.
- Desktop-Integration: `~/.local/share/applications/streamseeker.desktop` +
  Symlink auf `~/Desktop/`.
- Dependencies: `apt install ffmpeg` (oder `pacman`, `dnf`, …).

## Windows 10/11

Begrenzungen, die der User kennen muss:
- **FFmpeg** muss via `winget install Gyan.FFmpeg` installiert und im PATH sein.
- **Hardlinks** für Plex-Mirroring: funktionieren nur auf NTFS (nicht auf
  FAT32/exFAT). Fallback automatisch auf `shutil.copy2`.
- **Selenium**: ChromeDriver-Pfade sind manchmal zickig; wir dokumentieren das,
  fixen es aber nicht proaktiv.
- **Pfade**: `Path.home()` liefert `C:\Users\<name>` → `~/.streamseeker/` wird zu
  `C:\Users\<name>\.streamseeker\`. Alles andere läuft plattform-transparent
  über `pathlib`.

Autostart-Implementierung (ab Paket H):
- Primär: `schtasks.exe /Create /TN "StreamSeeker Daemon" /TR "<py> -m streamseeker daemon start --foreground" /SC ONLOGON /RL HIGHEST`.
- Fallback: `.lnk` in `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`.

Desktop-Integration: `%USERPROFILE%\Desktop\StreamSeeker.lnk` via `pywin32`
(IShellLink COM) oder PowerShell-Oneliner, Target = Dashboard-URL.

## Nicht unterstützt

- **Windows 7/8**: nein (EOL, Python 3.11 eh nicht).
- **Android/iOS**: nein — Rust/Java-Port wäre ein eigenes Projekt.
- **Docker-Container**: technisch möglich (alles dateibasiert), aber kein
  Docker-Image im Scope. Wer es braucht, baut es selbst.
