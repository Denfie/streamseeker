# ADR 0003: FastAPI + uvicorn für den Daemon

- **Status:** accepted
- **Datum:** 2026-04-23

## Kontext
Der Background-Service braucht eine HTTP-API für: (a) Chrome-Extension, (b)
zweite CLI-Instanzen zur Queue-Steuerung, (c) SSE für Live-Updates. Python bleibt
Backend (User-Vorgabe).

## Entscheidung
**FastAPI + uvicorn**. Beides wird als neue Dep in `pyproject.toml` aufgenommen.

## Alternativen
- **stdlib `http.server`:** keine neuen Deps, aber händisches Routing, kein
  automatisches Body-Parsing, SSE von Hand. Für unseren Umfang ~zu aufwändig.
- **Flask:** kleiner Fußabdruck, aber synchron. Für SSE mit vielen Clients
  weniger gut geeignet.
- **aiohttp:** gut geeignet, aber weniger verbreitet als FastAPI und schlechter
  dokumentiert für Hobby-Setups.

## Konsequenzen
- Zwei neue Python-Deps (`fastapi`, `uvicorn`) — Install-Größe ~8 MB.
- Pydantic als transitive Dep → Typ-Validierung der Requests "kostenlos".
- Dev-Experience: FastAPI hat `TestClient`, einfach für Integration-Tests.
- **Offen:** HTTP-Auth. Im MVP reicht `127.0.0.1`-Binding ohne Token (ADR 0004).
  Falls Multi-User nötig wird → neuer ADR mit Bearer-Token-Konzept.
