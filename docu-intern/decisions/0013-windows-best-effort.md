# ADR 0013: Windows als best-effort, nicht first-class

- **Status:** accepted
- **Datum:** 2026-04-23

## Kontext
Python 3.11 läuft auf Windows 10/11 problemlos. Aber viele Nachbar-Abhängigkeiten
(FFmpeg, Selenium-ChromeDriver) und OS-Spezifika (Hardlinks nur auf NTFS,
PowerShell-Encoding, Pfad-Separator) machen Windows-Support zu einem deutlich
größeren Stück Arbeit als Linux/macOS. Der Dev-Rechner ist macOS, und ein
CI-Windows-Runner ist nicht eingerichtet.

## Entscheidung
Windows wird offiziell als **best-effort**-Plattform deklariert:
- CLI, Daemon, Library, Extension-Install sollen laufen (plattform-neutraler Python-Code).
- Edge-Cases (FAT32-Drives, ACL-Probleme, alternative Chrome-Installpfade) werden
  **nicht** proaktiv getestet oder gefixt — nur auf konkreten Bug-Report.
- Autostart via Task Scheduler primär, `.lnk` im Startup-Ordner als Fallback.
- Desktop-Icon als `.lnk` auf `%USERPROFILE%\Desktop\`.

Dokumentiert in [platform-support.md](../platform-support.md).

## Alternativen
- **Windows als first-class:** bräuchte CI-Windows-Runner, MSI-Installer mit
  Code-Signing, FFmpeg-Bundling. Scope-Explosion, verworfen für MVP.
- **Windows komplett droppen:** unfreundlich zu Windows-Usern, die nur ein
  einfaches Download-Tool wollen. Verworfen.

## Konsequenzen
- **Gut:** Ich kann Features für macOS/Linux optimal bauen, ohne jedes Detail
  cross-plattform zu verproben.
- Bekannte Windows-Beschränkungen (Hardlinks, FFmpeg-PATH) sind dokumentiert;
  der Code fängt sie ab (z.B. `shutil.copy2` statt `os.link`-Fallback) ohne zu
  crashen.
- Falls die Windows-User-Basis signifikant wird → neuer ADR mit CI + Installer-Plan.
