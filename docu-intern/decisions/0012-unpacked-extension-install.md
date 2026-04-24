# ADR 0012: Chrome-Extension als "Load Unpacked"

- **Status:** accepted
- **Datum:** 2026-04-23

## Kontext
Die Chrome-Extension soll ohne Chrome-Web-Store-Publikation installierbar sein.
Chrome erlaubt drei Wege:
1. Installation aus dem Web Store (MSI-äquivalent, signiert).
2. Side-Loading einer `.crx`-Datei — seit Chrome 73 **blockiert** für externe
   Quellen (Edge/Brave identisch).
3. "Load Unpacked" aus einem Entwickler-Modus.

## Entscheidung
MVP setzt auf **Load Unpacked**:
- `streamseeker install-extension` kopiert den Extension-Ordner nach
  `~/.streamseeker/extension/` und öffnet `chrome://extensions/`.
- Eine klare Terminal-Anleitung führt den User durch "Developer Mode → Load
  Unpacked → auf den Ordner zeigen".
- Updates: `streamseeker install-extension --update` überschreibt den Ordner;
  der User klickt in Chrome auf "Reload".

## Alternativen
- **Chrome Web Store:** braucht $5 Developer-Fee, Identitätsprüfung, Screenshots,
  Privacy-Policy, Review-Prozess (Tage bis Wochen). Verworfen für MVP — kommt in
  Paket "post-MVP", falls gewünscht.
- **`.crx`-Sideload:** nicht möglich auf modernen Chrome-Versionen für
  nicht-enterprise-Umgebungen.
- **Firefox-XPI:** möglich, aber Firefox-Signatur ist Pflicht → Firefox-Add-ons-Store
  oder temporärer Install. Separater Weg, nicht Teil des MVP.

## Konsequenzen
- User sieht einen kleinen "Developer-Mode aktiv"-Hinweis in Chrome — akzeptabel
  für Personal Tool.
- Kein automatisches Extension-Update. Muss mit dem CLI-Update manuell getriggert
  werden (siehe `--update`-Flag).
- Extension-ID ist instabil (generiert bei jedem "Load Unpacked" neu), außer man
  setzt einen "key" in manifest.json. Wird gesetzt, damit die CORS-Allowlist
  stabil bleibt.
