# ADR 0006: CLI und Extension unabhängig versioniert

- **Status:** accepted
- **Datum:** 2026-04-23

## Kontext
Die Chrome-Extension und die CLI/Backend werden in unterschiedlichem Tempo
weiterentwickelt. Ein UI-Fix in der Extension soll nicht zwingend ein
CLI-Release auslösen — und umgekehrt. Beide haben außerdem unterschiedliche
Publikations-Kanäle (PyPI vs. Chrome Web Store / Load Unpacked).

## Entscheidung
Zwei separate Versionsstränge:
- **CLI/Backend** in `pyproject.toml`, Tag-Präfix `v`, Changelog `CHANGELOG.md`.
- **Extension** in `extension/manifest.json`, Tag-Präfix `ext-v`, Changelog
  `extension/CHANGELOG.md`.

Kompatibilität wird über `manifest.json.minCliVersion` deklariert. Popup warnt,
wenn der Daemon eine ältere CLI meldet (Endpoint `GET /version`).

## Alternativen
- **Eine Version für beides:** einfach, aber koppelt Release-Zyklen. UI-Patches
  würden das Backend mitreißen.
- **Kein Extension-Versioning:** nicht praktikabel — Manifest v3 verlangt es.

## Konsequenzen
- Zwei Changelogs zu pflegen. Template-Disziplin hilft (`docu-intern/versioning.md`).
- Kompatibilitäts-Matrix wird durch `minCliVersion` maschinell geprüft — keine
  handgepflegte Tabelle nötig.
- Git-Tags mit zwei Präfixen (`v`/`ext-v`) sind für Tools wie `git describe`
  minimal aufwändiger, aber klar.
